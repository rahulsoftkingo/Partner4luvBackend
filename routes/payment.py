"""
Google Play In-App Purchase (IAP) integration — with try/except error handling
around every DB call, every Google API call, and payload parsing step.

Covers two flows, both of which you need in production:

1. POST /user/iap/verify
   Called by the Android app immediately after `BillingClient` returns a
   successful purchase. We verify the purchaseToken server-side with the
   Google Play Developer API (never trust the client-reported "success"),
   acknowledge it, record it, and grant the entitlement.

2. POST /user/iap/rtdn
   A push endpoint for Google Play "Real-time Developer Notifications"
   (RTDN), delivered via a Pub/Sub push subscription. This is what tells
   you about renewals, cancellations, refunds, grace periods, etc. that
   happen when the user isn't in your app. Without this, a subscription
   silently expiring won't downgrade the user.

Setup required (not code):
- Create a Google Cloud service account with "Android Publisher" access,
  download its JSON key.
- In Play Console > Setup > API access, link the service account and grant
  it "View financial data" + "Manage orders and subscriptions" permission.
- In Play Console > Setup > Monetization setup, enable Real-time developer
  notifications and point it at a Pub/Sub topic; create a push subscription
  on that topic pointing at https://yourdomain.com/user/iap/rtdn.
- Env vars: ANDROID_PACKAGE_NAME, GOOGLE_SERVICE_ACCOUNT_FILE.
- pip install google-api-python-client google-auth --break-system-packages
  (or install inside a venv without the flag)

Prisma schema additions expected (adjust names to match your schema):

    model Payment {
      id                     Int      @id @default(autoincrement())
      userId                 Int
      user                   User     @relation(fields: [userId], references: [id])
      provider               String   // "GOOGLE_PLAY"
      providerTransactionId  String   @unique   // purchaseToken
      productId              String
      status                 String   // COMPLETED, REFUNDED, CANCELED, EXPIRED
      rawResponse            Json?
      createdAt              DateTime @default(now())
      updatedAt              DateTime @updatedAt
    }

    // On User:
    //   subscriptionExpiresAt DateTime?
    //   superLikeBalance      Int      @default(0)
"""

import base64
import json
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request, status
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from prisma import Json
from prisma.errors import PrismaError
from pydantic import BaseModel

from db import db

router = APIRouter(prefix="/user/iap", tags=["in-app-purchase"])

# --- Config ---

PACKAGE_NAME = os.environ.get("ANDROID_PACKAGE_NAME")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
SCOPES = ["https://www.googleapis.com/auth/androidpublisher"]

_android_publisher = None
_init_error: Optional[str] = None

try:
    if not PACKAGE_NAME or not SERVICE_ACCOUNT_FILE:
        raise RuntimeError(
            "ANDROID_PACKAGE_NAME and GOOGLE_SERVICE_ACCOUNT_FILE env vars must be set"
        )
    _credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    _android_publisher = build(
        "androidpublisher", "v3", credentials=_credentials, cache_discovery=False
    )
except Exception as e:
    # Don't crash the whole app on import if IAP isn't configured yet in this
    # environment (e.g. local dev). Routes will fail loudly and clearly instead.
    _init_error = str(e)


def _require_client():
    if _android_publisher is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Google Play billing is not configured: {_init_error}",
        )


# Map your Play Console product/subscription IDs to what they grant.
PRODUCT_PLAN_MAP = {
    "premium_monthly": {"tier": "Premium", "swipeLimit": 999999, "isSubscription": True},
    "premium_yearly": {"tier": "Premium", "swipeLimit": 999999, "isSubscription": True},
    "superlike_pack_5": {"consumable": True, "superLikes": 5, "isSubscription": False},
}

# RTDN subscriptionNotification.notificationType values we care about
RTDN_SUBSCRIPTION_TYPES = {
    1: "RECOVERED",
    2: "RENEWED",
    3: "CANCELED",
    4: "PURCHASED",
    5: "ON_HOLD",
    6: "IN_GRACE_PERIOD",
    7: "RESTARTED",
    8: "PRICE_CHANGE_CONFIRMED",
    9: "DEFERRED",
    12: "REVOKED",
    13: "EXPIRED",
}

DOWNGRADE_TYPES = {"CANCELED", "ON_HOLD", "REVOKED", "EXPIRED"}


# --- Schemas ---

class VerifyPurchaseRequest(BaseModel):
    userId: int
    productId: str
    purchaseToken: str
    purchaseType: Literal["subscription", "product"] = "subscription"


# --- Google Play API helpers (each wraps HttpError -> HTTPException) ---

def _verify_subscription(product_id: str, token: str) -> dict:
    try:
        return _android_publisher.purchases().subscriptions().get(
            packageName=PACKAGE_NAME, subscriptionId=product_id, token=token
        ).execute()
    except HttpError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or unrecognized purchase token: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Google Play API: {e}",
        )


def _verify_product(product_id: str, token: str) -> dict:
    try:
        return _android_publisher.purchases().products().get(
            packageName=PACKAGE_NAME, productId=product_id, token=token
        ).execute()
    except HttpError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or unrecognized purchase token: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Google Play API: {e}",
        )


def _acknowledge_subscription(product_id: str, token: str) -> None:
    try:
        _android_publisher.purchases().subscriptions().acknowledge(
            packageName=PACKAGE_NAME, subscriptionId=product_id, token=token, body={}
        ).execute()
    except HttpError as e:
        # Not fatal to the request — purchase is already verified/recorded.
        # Google will keep the purchase in "unacknowledged" state and we can
        # retry acknowledgement later; just log it.
        print(f"WARNING: failed to acknowledge subscription {product_id}: {e}")
    except Exception as e:
        print(f"WARNING: unexpected error acknowledging subscription: {e}")


def _acknowledge_product(product_id: str, token: str) -> None:
    try:
        _android_publisher.purchases().products().acknowledge(
            packageName=PACKAGE_NAME, productId=product_id, token=token, body={}
        ).execute()
    except HttpError as e:
        print(f"WARNING: failed to acknowledge product {product_id}: {e}")
    except Exception as e:
        print(f"WARNING: unexpected error acknowledging product: {e}")


async def _apply_entitlement(user_id: int, product_id: str, expires_at: Optional[datetime]) -> None:
    plan = PRODUCT_PLAN_MAP[product_id]
    try:
        if plan.get("consumable"):
            await db.user.update(
                where={"id": user_id},
                data={"superLikeBalance": {"increment": plan.get("superLikes", 0)}},
            )
        else:
            update_fields = {"tier": plan["tier"], "swipeLimit": plan["swipeLimit"]}
            if expires_at:
                update_fields["subscriptionExpiresAt"] = expires_at
            await db.user.update(where={"id": user_id}, data=update_fields)
    except PrismaError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Purchase was verified but granting entitlement failed: {e}",
        )


async def _revoke_entitlement(user_id: int) -> None:
    try:
        await db.user.update(
            where={"id": user_id},
            data={"tier": "Free", "swipeLimit": 10, "subscriptionExpiresAt": None},
        )
    except PrismaError as e:
        print(f"WARNING: failed to revoke entitlement for user {user_id}: {e}")


# --- Routes ---

@router.post("/verify")
async def verify_purchase(data: VerifyPurchaseRequest):
    """
    Client calls this right after BillingClient reports a successful
    purchase. We independently confirm it with Google before granting
    anything — never trust the client's own "purchase succeeded" signal.
    """
    _require_client()

    try:
        user = await db.user.find_unique(where={"id": data.userId})
    except PrismaError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user: {e}",
        )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    plan_config = PRODUCT_PLAN_MAP.get(data.productId)
    if not plan_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown product ID")

    # Idempotency: a client retry (e.g. after a flaky network response)
    # must not double-grant the same purchase.
    try:
        existing = await db.payment.find_first(
            where={"providerTransactionId": data.purchaseToken}
        )
    except PrismaError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking existing payment: {e}",
        )

    if existing:
        return {"message": "Purchase already processed", "payment": existing}

    expires_at: Optional[datetime] = None

    try:
        if data.purchaseType == "subscription":
            result = _verify_subscription(data.productId, data.purchaseToken)
            # paymentState: 0=pending, 1=received, 2=free trial, 3=pending deferred
            if result.get("paymentState") not in (1, 2):
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Payment not completed",
                )
            expiry_ms = int(result.get("expiryTimeMillis", 0))
            expires_at = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc)
            if result.get("acknowledgementState") == 0:
                _acknowledge_subscription(data.productId, data.purchaseToken)
        else:
            result = _verify_product(data.productId, data.purchaseToken)
            # purchaseState: 0=purchased, 1=canceled, 2=pending
            if result.get("purchaseState") != 0:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Payment not completed",
                )
            if result.get("acknowledgementState") == 0:
                _acknowledge_product(data.productId, data.purchaseToken)
    except HTTPException:
        raise
    except (ValueError, TypeError) as e:
        # Malformed/unexpected response shape from Google
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected response from Google Play API: {e}",
        )

    try:
        payment = await db.payment.create(
            data={
                "userId": data.userId,
                "provider": "GOOGLE_PLAY",
                "providerTransactionId": data.purchaseToken,
                "productId": data.productId,
                "status": "COMPLETED",
                "rawResponse": Json(result),
            }
        )
    except PrismaError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Purchase was verified with Google but could not be recorded: {e}",
        )

    await _apply_entitlement(data.userId, data.productId, expires_at)

    return {"message": "Purchase verified and applied", "payment": payment}


@router.post("/rtdn")
async def handle_rtdn(request: Request):
    """
    Pub/Sub push endpoint for Google Play Real-time Developer Notifications.
    Handles renewals, cancellations, grace periods, refunds, and expirations
    that occur independently of the app being open.

    Pub/Sub push delivers: {"message": {"data": "<base64 json>", ...}, "subscription": "..."}

    NOTE: we return {"status": ...} with HTTP 200 in most "nothing to do"
    cases rather than raising errors, because Pub/Sub will aggressively
    retry non-2xx responses — we only want it to retry on genuine failures.
    """
    try:
        envelope = await request.json()
    except Exception as e:
        # Malformed request body — nothing Pub/Sub retrying will fix.
        return {"status": "ignored", "reason": f"invalid JSON envelope: {e}"}

    message = envelope.get("message") if isinstance(envelope, dict) else None
    if not message or "data" not in message:
        return {"status": "ignored", "reason": "no message.data in envelope"}

    try:
        payload = json.loads(base64.b64decode(message["data"]).decode("utf-8"))
    except Exception as e:
        return {"status": "ignored", "reason": f"could not decode payload: {e}"}

    sub_notification = payload.get("subscriptionNotification") if isinstance(payload, dict) else None
    if not sub_notification:
        # Could be a oneTimeProductNotification or testNotification; nothing to do.
        return {"status": "ok"}

    product_id = sub_notification.get("subscriptionId")
    purchase_token = sub_notification.get("purchaseToken")
    notification_type = RTDN_SUBSCRIPTION_TYPES.get(sub_notification.get("notificationType"))

    if not product_id or not purchase_token or not notification_type:
        return {"status": "ok", "reason": "missing fields in subscriptionNotification"}

    try:
        payment = await db.payment.find_first(
            where={"providerTransactionId": purchase_token}
        )
    except PrismaError as e:
        # A genuine transient failure — let Pub/Sub retry by returning 5xx.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error looking up payment: {e}",
        )

    if not payment:
        # We have no record of the original purchase (e.g. verify never
        # completed). Nothing to reconcile against yet.
        return {"status": "ok", "reason": "no matching payment record"}

    if _android_publisher is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Google Play billing is not configured: {_init_error}",
        )
        
    result = _verify_subscription(product_id, purchase_token)

    try:
        expiry_ms = int(result.get("expiryTimeMillis", 0))
        expires_at = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected expiryTimeMillis in Google response: {e}",
        )

    if notification_type in DOWNGRADE_TYPES and expires_at < datetime.now(timezone.utc):
        await _revoke_entitlement(payment.userId)
        new_status = notification_type
    else:
        await _apply_entitlement(payment.userId, product_id, expires_at)
        new_status = "COMPLETED"

    try:
        await db.payment.update(
            where={"id": payment.id},
            data={"status": new_status, "rawResponse": Json(result)},
        )
    except PrismaError as e:
        print(f"WARNING: failed to update payment record {payment.id}: {e}")

    return {"status": "ok"}
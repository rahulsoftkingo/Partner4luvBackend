# from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Request
# import stripe_utils
# from typing import Optional, List
# from pydantic import BaseModel
# import os
# import shutil
# from uuid import uuid4
# from db import db

# from datetime import datetime, timedelta, timezone

# router = APIRouter(prefix="/economy", tags=["economy"])

# @router.get("/stats")
# async def get_economy_stats():
#     try:
#         # 1. Total Coins in Circulation
#         users = await db.user.find_many()
#         total_coins = sum(u.coins if u.coins else 0 for u in users)

#         # 2. Economy Revenue (MTD)
#         now = datetime.now(timezone.utc)
#         first_day_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        
#         payments = await db.payment.find_many(
#             where={
#                 "status": "SUCCESSFUL",
#                 "createdAt": {"gte": first_day_of_month}
#             }
#         )
#         mtd_revenue = sum(p.amount if p.amount else 0 for p in payments)

#         # 3. Gifts Sent Today
#         today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
#         # Using find_many and len as fallback if count() has issues in this version
#         gifts = await db.sentgift.find_many(
#             where={"createdAt": {"gte": today_start}}
#         )
#         gifts_count = len(gifts)

#         return {
#             "total_coins": total_coins,
#             "mtd_revenue": mtd_revenue,
#             "gifts_sent_today": gifts_count,
#             "coins_trend": "+12% from last week",
#             "revenue_trend": "+5.2% vs last month",
#             "gifts_trend": f"+{gifts_count} vs yesterday"
#         }
#     except Exception as e:
#         print(f"ECONOMY STATS ERROR: {str(e)}")
#         return {
#             "total_coins": 0,
#             "mtd_revenue": 0,
#             "gifts_sent_today": 0,
#             "error": str(e)
#         }

# class PackageCreate(BaseModel):
#     name: str
#     coins: int
#     price: float
#     currency: Optional[str] = "USD"
#     stripePriceId: Optional[str] = None

# class FeatureCreate(BaseModel):
#     name: str
#     description: Optional[str] = None
#     iconUrl: Optional[str] = None

# class SubscriptionPlanCreate(BaseModel):
#     name: str
#     description: Optional[str] = None
#     price: float
#     duration: str # WEEKLY, MONTHLY, YEARLY
#     durationValue: int = 1
#     features: List[FeatureCreate] = []
#     stripePriceId: Optional[str] = None
#     dailySwipes: int = 10

# class SendGiftRequest(BaseModel):
#     sender_id: int
#     receiver_id: int
#     item_id: int

# @router.get("/items")
# async def get_items():
#     return await db.virtualitem.find_many(order={"createdAt": "desc"})

# @router.post("/items")
# async def create_item(
#     name: str = Form(...),
#     type: str = Form(...),
#     price: int = Form(...),
#     file: UploadFile = File(...)
# ):
#     # Save file
#     file_ext = file.filename.split(".")[-1]
#     file_name = f"{uuid4()}.{file_ext}"
#     file_path = f"uploads/economy/{file_name}"
#     os.makedirs("uploads/economy", exist_ok=True)
    
#     with open(file_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)
    
#     image_url = f"/uploads/economy/{file_name}"
    
#     item = await db.virtualitem.create(
#         data={
#             "name": name,
#             "type": type,
#             "price": price,
#             "imageUrl": image_url
#         }
#     )
#     return item

# @router.get("/packages")
# async def get_packages():
#     return await db.coinpackage.find_many(order={"createdAt": "desc"})

# @router.post("/packages")
# async def create_package(data: PackageCreate):
#     # Ensure empty string doesn't cause unique constraint violation
#     stripe_id = data.stripePriceId if data.stripePriceId and data.stripePriceId.strip() != "" else None
    
#     package = await db.coinpackage.create(
#         data={
#             "name": data.name,
#             "coins": data.coins,
#             "price": data.price,
#             "currency": data.currency,
#             "stripePriceId": stripe_id
#         }
#     )
#     return package

# @router.get("/plans")
# async def get_plans():
#     return await db.subscriptionplan.find_many(
#         include={"features": True},
#         order={"createdAt": "desc"}
#     )

# @router.post("/plans")
# async def create_plan(data: SubscriptionPlanCreate):
#     # Ensure empty string doesn't cause unique constraint violation
#     stripe_id = data.stripePriceId if data.stripePriceId and data.stripePriceId.strip() != "" else None
    
#     plan = await db.subscriptionplan.create(
#         data={
#             "name": data.name,
#             "description": data.description,
#             "price": data.price,
#             "duration": data.duration,
#             "durationValue": data.durationValue,
#             "stripePriceId": stripe_id,
#             "dailySwipes": data.dailySwipes,
#             "features": {
#                 "create": [
#                     {
#                         "name": f.name,
#                         "description": f.description,
#                         "iconUrl": f.iconUrl
#                     } for f in data.features
#                 ]
#             }
#         },
#         include={"features": True}
#     )
#     return plan

# @router.get("/plans/{plan_id}")
# async def get_plan(plan_id: int):
#     plan = await db.subscriptionplan.find_unique(
#         where={"id": plan_id},
#         include={"features": True}
#     )
#     if not plan:
#         raise HTTPException(status_code=404, detail="Plan not found")
#     return plan

# @router.put("/plans/{plan_id}")
# async def update_plan(plan_id: int, data: SubscriptionPlanCreate):
#     # Ensure empty string doesn't cause unique constraint violation
#     stripe_id = data.stripePriceId if data.stripePriceId and data.stripePriceId.strip() != "" else None
    
#     # 1. Update the plan metadata
#     plan = await db.subscriptionplan.update(
#         where={"id": plan_id},
#         data={
#             "name": data.name,
#             "description": data.description,
#             "price": data.price,
#             "duration": data.duration,
#             "durationValue": data.durationValue,
#             "stripePriceId": stripe_id,
#             "dailySwipes": data.dailySwipes
#         }
#     )
    
#     # 2. Sync features: Delete existing and recreate
#     await db.planfeature.delete_many(where={"planId": plan_id})
    
#     if data.features:
#         await db.planfeature.create_many(
#             data=[
#                 {
#                     "planId": plan_id,
#                     "name": f.name,
#                     "description": f.description,
#                     "iconUrl": f.iconUrl
#                 } for f in data.features
#             ]
#         )
    
#     return await db.subscriptionplan.find_unique(
#         where={"id": plan_id},
#         include={"features": True}
#     )

# @router.delete("/plans/{plan_id}")
# async def delete_plan(plan_id: int):
#     try:
#         plan = await db.subscriptionplan.find_unique(where={"id": plan_id})
#         if not plan:
#             raise HTTPException(status_code=404, detail="Plan not found")

#         # 1. System Protection: Block deletion if plan is 'Free'
#         if plan.name.lower() == "free":
#             raise HTTPException(
#                 status_code=400, 
#                 detail="The 'Free' plan is a system requirement and cannot be deleted. You can only edit its details or features."
#             )

#         # 2. Activity Check: Check if any users are currently on this plan
#         active_users = await db.user.count(where={"tier": plan.name})
#         if active_users > 0:
#             raise HTTPException(
#                 status_code=400, 
#                 detail=f"Cannot delete: {active_users} users are currently subscribed to {plan.name}. Please deactivate (Toggle) the plan instead to stop new signups."
#             )

#         # 2. If no users, allow deletion
#         await db.subscriptionplan.delete(where={"id": plan_id})
#         return {"status": "success"}
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# @router.patch("/plans/{plan_id}/toggle")
# async def toggle_plan(plan_id: int):
#     plan = await db.subscriptionplan.find_unique(where={"id": plan_id})
#     if not plan:
#         raise HTTPException(status_code=404, detail="Plan not found")
    
#     updated_plan = await db.subscriptionplan.update(
#         where={"id": plan_id},
#         data={"isActive": not plan.isActive}
#     )
#     return updated_plan

# @router.post("/send-gift")
# async def send_gift(data: SendGiftRequest):
#     # 1. Fetch sender, receiver, and item
#     sender = await db.user.find_unique(where={"id": data.sender_id})
#     item = await db.virtualitem.find_unique(where={"id": data.item_id})
    
#     if not sender or not item:
#         raise HTTPException(status_code=404, detail="User or Item not found")
    
#     # 2. Check balance
#     if sender.coins < item.price:
#         raise HTTPException(status_code=400, detail="Insufficient coins")
    
#     # 3. Transaction logic
#     # Deduct from sender
#     await db.user.update(
#         where={"id": sender.id},
#         data={"coins": {"decrement": item.price}}
#     )
    
#     # Create transaction log
#     await db.cointransaction.create(
#         data={
#             "userId": sender.id,
#             "amount": -item.price,
#             "type": "GIFT_SENT",
#             "description": f"Sent {item.name} to user ID {data.receiver_id}"
#         }
#     )
    
#     # Record sent gift
#     sent_gift = await db.sentgift.create(
#         data={
#             "senderId": data.sender_id,
#             "receiverId": data.receiver_id,
#             "itemId": data.item_id
#         }
#     )
    
#     return {"message": "Gift sent successfully", "sent_gift_id": sent_gift.id}

# @router.get("/ledger/stats")
# async def get_ledger_stats():
#     try:
#         payments = await db.payment.find_many(where={"status": "SUCCESSFUL"})
#         total_gross = sum(p.amount for p in payments)
        
#         # Net Revenue (total received after gateway cuts)
#         total_net = sum(p.netAmount if p.netAmount else p.amount * 0.7 for p in payments)
        
#         # Deductions
#         total_deductions = total_gross - total_net
        
#         return {
#             "total_gross": total_gross,
#             "total_net": total_net,
#             "total_deductions": total_deductions,
#             "gross_trend": "+12%",
#             "deductions_trend": "-2%"
#         }
#     except Exception as e:
#         return {"error": str(e), "total_gross": 0, "total_net": 0, "total_deductions": 0}

# @router.get("/transactions")
# async def get_transactions():
#     try:
#         # Fetch payments and coin transactions
#         payments = await db.payment.find_many(
#             include={"user": True},
#             order={"createdAt": "desc"},
#             take=50
#         )
#         return payments
#     except Exception as e:
#         return []

# @router.get("/transactions/{user_id}")
# async def get_user_transactions(user_id: int):
#     return await db.cointransaction.find_many(
#         where={"userId": user_id},
#         order={"createdAt": "desc"}
#     )

# # --- NEW ACTIONS ---

# @router.delete("/items/{item_id}")
# async def delete_item(item_id: int):
#     await db.virtualitem.delete(where={"id": item_id})
#     return {"message": "Item deleted"}

# @router.patch("/items/{item_id}/toggle")
# async def toggle_item_status(item_id: int):
#     item = await db.virtualitem.find_unique(where={"id": item_id})
#     if not item: raise HTTPException(status_code=404)
#     return await db.virtualitem.update(
#         where={"id": item_id},
#         data={"isActive": not item.isActive}
#     )

# @router.delete("/packages/{pkg_id}")
# async def delete_package(pkg_id: int):
#     await db.coinpackage.delete(where={"id": pkg_id})
#     return {"message": "Package deleted"}

# @router.patch("/packages/{pkg_id}/toggle")
# async def toggle_package_status(pkg_id: int):
#     pkg = await db.coinpackage.find_unique(where={"id": pkg_id})
#     if not pkg: raise HTTPException(status_code=404)
#     return await db.coinpackage.update(
#         where={"id": pkg_id},
#         data={"isActive": not pkg.isActive}
#     )

# # --- STRIPE CHECKOUT ---

# @router.post("/checkout/package/{pkg_id}")
# async def create_package_checkout(pkg_id: int, user_id: int):
#     pkg = await db.coinpackage.find_unique(where={"id": pkg_id})
#     user = await db.user.find_unique(where={"id": user_id})
#     if not pkg or not pkg.stripePriceId or not user:
#         raise HTTPException(status_code=404, detail="Package, User, or Price ID not found")
    
#     success_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
#     cancel_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/payment-cancel"
    
#     checkout_url = stripe_utils.create_checkout_session(
#         user_id=user_id,
#         price_id=pkg.stripePriceId,
#         success_url=success_url,
#         cancel_url=cancel_url,
#         mode="payment",
#         extra_metadata={"pkg_id": pkg_id},
#         customer_id=user.stripeCustomerId
#     )
    
#     if not checkout_url:
#         raise HTTPException(status_code=500, detail="Failed to create checkout session")
    
#     return {"url": checkout_url}

# @router.post("/checkout/subscription/{plan_id}")
# async def create_subscription_checkout(plan_id: int, user_id: int):
#     plan = await db.subscriptionplan.find_unique(where={"id": plan_id})
#     user = await db.user.find_unique(where={"id": user_id})
#     if not plan or not plan.stripePriceId or not user:
#         raise HTTPException(status_code=404, detail="Plan, User, or Price ID not found")
    
#     success_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
#     cancel_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/payment-cancel"
    
#     checkout_url = stripe_utils.create_checkout_session(
#         user_id=user_id,
#         price_id=plan.stripePriceId,
#         success_url=success_url,
#         cancel_url=cancel_url,
#         mode="subscription",
#         extra_metadata={"plan_id": plan_id},
#         customer_id=user.stripeCustomerId
#     )
    
#     if not checkout_url:
#         raise HTTPException(status_code=500, detail="Failed to create checkout session")
    
#     return {"url": checkout_url}

# @router.post("/webhook")
# async def stripe_webhook(request: Request):
#     payload = await request.body()
#     sig_header = request.headers.get("stripe-signature")
    
#     event = stripe_utils.verify_webhook_signature(payload, sig_header)
#     if not event:
#         raise HTTPException(status_code=400, detail="Invalid signature")
    
#     if event['type'] == 'checkout.session.completed':
#         session = event['data']['object']
#         user_id = int(session['client_reference_id'])
#         metadata = session.get('metadata', {})
#         mode = metadata.get('mode')
        
#         # Determine what was bought
#         if mode == "payment":
#             # Find the package by price ID (assuming unique)
#             # Or we could have passed pkg_id in metadata
#             # Let's assume we pass pkg_id in metadata for reliability
#             pkg_id = metadata.get('pkg_id')
#             if pkg_id:
#                 pkg = await db.coinpackage.find_unique(where={"id": int(pkg_id)})
#                 if pkg:
#                     # Update user coins
#                     await db.user.update(
#                         where={"id": user_id},
#                         data={"coins": {"increment": pkg.coins}}
#                     )
#                     # Log transaction
#                     await db.cointransaction.create(
#                         data={
#                             "userId": user_id,
#                             "amount": pkg.coins,
#                             "type": "PURCHASE",
#                             "description": f"Purchased {pkg.name} package",
#                             "referenceId": session['id']
#                         }
#                     )
#                     await db.payment.create(
#                         data={
#                             "txId": session['id'],
#                             "amount": pkg.price,
#                             "netAmount": pkg.price * 0.95,
#                             "method": "STRIPE",
#                             "status": "SUCCESSFUL",
#                             "tier": "COINS",
#                             "userId": user_id
#                         }
#                     )
#                     # Also ensure Customer ID is saved
#                     await db.user.update(
#                         where={"id": user_id},
#                         data={"stripeCustomerId": session.get('customer')}
#                     )
        
#         elif mode == "subscription":
#             plan_id = metadata.get('plan_id')
#             if plan_id:
#                 plan = await db.subscriptionplan.find_unique(where={"id": int(plan_id)})
#                 if plan:
#                     # Update user tier
#                     await db.user.update(
#                         where={"id": user_id},
#                         data={
#                             "tier": plan.name,
#                             "swipeLimit": plan.dailySwipes, # Persistent snapshot of the limit
#                             "stripeSubscriptionId": session.get('subscription'),
#                             "stripeCustomerId": session.get('customer')
#                         }
#                     )
#                     # Log payment
#                     await db.payment.create(
#                         data={
#                             "txId": session['id'],
#                             "amount": plan.price,
#                             "netAmount": plan.price * 0.95,
#                             "method": "STRIPE",
#                             "status": "SUCCESSFUL",
#                             "tier": plan.name,
#                             "userId": user_id
#                         }
#                     )

#     elif event['type'] == 'customer.subscription.deleted':
#         subscription = event['data']['object']
#         stripe_cust_id = subscription.get('customer')
        
#         if stripe_cust_id:
#             user = await db.user.find_unique(where={"stripeCustomerId": stripe_cust_id})
#             if user:
#                 # Downgrade to Free
#                 await db.user.update(
#                     where={"id": user.id},
#                     data={
#                         "tier": "Free",
#                         "swipeLimit": 10,
#                         "stripeSubscriptionId": None
#                     }
#                 )
#                 print(f"User {user.id} downgraded due to subscription deletion.")

#     elif event['type'] == 'invoice.payment_failed':
#         invoice = event['data']['object']
#         stripe_cust_id = invoice.get('customer')
        
#         if stripe_cust_id:
#             # You might want to send a notification or a grace period here.
#             # For now, let's just log it.
#             print(f"Payment failed for customer {stripe_cust_id}")

#     return {"status": "success"}


from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from typing import Optional, List
from pydantic import BaseModel
import os
import shutil
from uuid import uuid4
from db import db
from prisma import Json
from datetime import datetime, timezone
from prisma.errors import PrismaError
from google.oauth2 import service_account
from googleapiclient.discovery import build

router = APIRouter(prefix="/economy", tags=["economy"])

# ---------------------------------------------------------------------------
# GOOGLE PLAY BILLING SETUP
# Used for BOTH one-time coin purchases (products) and subscriptions.
# ---------------------------------------------------------------------------

PACKAGE_NAME = os.environ.get("ANDROID_PACKAGE_NAME")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
SCOPES = ["https://www.googleapis.com/auth/androidpublisher"]

_android_publisher = None
_init_error = None
try:
    if SERVICE_ACCOUNT_FILE and PACKAGE_NAME:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        _android_publisher = build("androidpublisher", "v3", credentials=credentials)
    else:
        _init_error = "ANDROID_PACKAGE_NAME or GOOGLE_SERVICE_ACCOUNT_FILE not set"
except Exception as e:
    _android_publisher = None
    _init_error = str(e)


def _verify_product_purchase(product_id: str, purchase_token: str):
    """One-time product (coins) verification."""
    return _android_publisher.purchases().products().get(
        packageName=PACKAGE_NAME,
        productId=product_id,
        token=purchase_token,
    ).execute()


def _acknowledge_product_purchase(product_id: str, purchase_token: str):
    _android_publisher.purchases().products().acknowledge(
        packageName=PACKAGE_NAME,
        productId=product_id,
        token=purchase_token,
        body={}
    ).execute()


def _verify_subscription_purchase(subscription_id: str, purchase_token: str):
    """Subscription (recurring plan) verification."""
    return _android_publisher.purchases().subscriptions().get(
        packageName=PACKAGE_NAME,
        subscriptionId=subscription_id,
        token=purchase_token,
    ).execute()


def _acknowledge_subscription_purchase(subscription_id: str, purchase_token: str):
    _android_publisher.purchases().subscriptions().acknowledge(
        packageName=PACKAGE_NAME,
        subscriptionId=subscription_id,
        token=purchase_token,
        body={}
    ).execute()


# ---------------------------------------------------------------------------
# COINS — one-time IAP purchase
# ---------------------------------------------------------------------------

class VerifyIAPRequest(BaseModel):
    user_id: int
    product_id: str        # Google Play "Product ID" for the coin pack
    purchase_token: str    # Returned to the app by Google Play Billing Library


@router.post("/coins/iap/verify")
async def verify_iap_purchase(data: VerifyIAPRequest):
    """
    Called by the Android app right after Google Play Billing Library
    completes a ONE-TIME product purchase (coins). Verifies server-side,
    credits coins exactly once, and acknowledges with Google.
    """
    if _android_publisher is None:
        raise HTTPException(
            status_code=503,
            detail=f"Google Play billing is not configured: {_init_error}",
        )

    # 1. Idempotency guard
    existing = await db.payment.find_first(
        where={"providerTransactionId": data.purchase_token}
    )
    if existing:
        return {"status": "already_processed", "message": "This purchase was already credited"}

    # 2. Verify with Google
    try:
        result = _verify_product_purchase(data.product_id, data.purchase_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google verification failed: {e}")

    # purchaseState: 0 = Purchased, 1 = Cancelled, 2 = Pending
    purchase_state = result.get("purchaseState")
    if purchase_state != 0:
        return {"status": "not_completed", "purchaseState": purchase_state}

    # 3. Look up coin package
    pkg = await db.coinpackage.find_first(where={"googleProductId": data.product_id})
    if not pkg:
        raise HTTPException(status_code=404, detail="No matching coin package found for this product_id")

    user = await db.user.find_unique(where={"id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 4. Credit coins
    await db.user.update(
        where={"id": user.id},
        data={"coins": {"increment": pkg.coins}}
    )

    # 5. Transaction log
    await db.cointransaction.create(
        data={
            "userId": user.id,
            "amount": pkg.coins,
            "type": "PURCHASE",
            "description": f"Purchased {pkg.name} via Google Play",
            "referenceId": data.purchase_token
        }
    )

    # 6. Payment record
    await db.payment.create(
        data={
            "txId": data.purchase_token,
            "providerTransactionId": data.purchase_token,
            "amount": pkg.price,
            "netAmount": pkg.price * 0.85,
            "method": "GOOGLE_PLAY",
            "status": "SUCCESSFUL",
            "tier": "COINS",
            "userId": user.id,
            "rawResponse": Json(result)
        }
    )

    # 7. Acknowledge (or Google auto-refunds after 3 days)
    try:
        _acknowledge_product_purchase(data.product_id, data.purchase_token)
    except Exception as e:
        print(f"WARNING: failed to acknowledge Google Play purchase {data.purchase_token}: {e}")

    return {"status": "success", "coins_added": pkg.coins}


# ---------------------------------------------------------------------------
# SUBSCRIPTIONS — recurring IAP purchase
# ---------------------------------------------------------------------------

class VerifySubscriptionRequest(BaseModel):
    user_id: int
    subscription_id: str    # Google Play "Product ID" for the subscription (Base Plan)
    purchase_token: str


@router.post("/iap/verify-subscription")
async def verify_subscription_purchase(data: VerifySubscriptionRequest):
    """
    Called by the Android app right after Google Play Billing Library
    completes a SUBSCRIPTION purchase. Verifies server-side, upgrades the
    user's tier, and acknowledges with Google.

    NOTE: renewals/cancellations/refunds that happen LATER (when the app
    isn't open) are handled separately by the RTDN webhook (/subscriptions/rtdn),
    not by this endpoint. This endpoint only handles the initial purchase.
    """
    if _android_publisher is None:
        raise HTTPException(
            status_code=503,
            detail=f"Google Play billing is not configured: {_init_error}",
        )

    # 1. Idempotency guard
    existing = await db.payment.find_first(
        where={"providerTransactionId": data.purchase_token}
    )
    if existing:
        return {"status": "already_processed", "message": "This purchase was already applied"}

    # 2. Verify with Google
    try:
        result = _verify_subscription_purchase(data.subscription_id, data.purchase_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google verification failed: {e}")

    expiry_ms = int(result.get("expiryTimeMillis", 0))
    expires_at = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        return {"status": "not_active", "message": "Subscription is not currently active"}

    # 3. Look up the plan
    plan = await db.subscriptionplan.find_first(where={"googleProductId": data.subscription_id})
    if not plan:
        raise HTTPException(status_code=404, detail="No matching plan found for this subscription_id")

    user = await db.user.find_unique(where={"id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 4. Upgrade user tier
    await db.user.update(
        where={"id": user.id},
        data={
            "tier": plan.name,
            "swipeLimit": plan.dailySwipes,
            "googlePurchaseToken": data.purchase_token,
        }
    )

    # 5. Payment record
    await db.payment.create(
        data={
            "txId": data.purchase_token,
            "providerTransactionId": data.purchase_token,
            "amount": plan.price,
            "netAmount": plan.price * 0.85,
            "method": "GOOGLE_PLAY",
            "status": "SUCCESSFUL",
            "tier": plan.name,
            "userId": user.id,
            "rawResponse": Json(result)
        }
    )

    # 6. Acknowledge with Google
    try:
        _acknowledge_subscription_purchase(data.subscription_id, data.purchase_token)
    except Exception as e:
        print(f"WARNING: failed to acknowledge Google Play subscription {data.purchase_token}: {e}")

    return {"status": "success", "tier": plan.name, "expires_at": expires_at.isoformat()}


# ---------------------------------------------------------------------------
# STATS / DASHBOARD
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_economy_stats():
    try:
        users = await db.user.find_many()
        total_coins = sum(u.coins if u.coins else 0 for u in users)

        now = datetime.now(timezone.utc)
        first_day_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        payments = await db.payment.find_many(
            where={
                "status": "SUCCESSFUL",
                "createdAt": {"gte": first_day_of_month}
            }
        )
        mtd_revenue = sum(p.amount if p.amount else 0 for p in payments)

        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        gifts = await db.sentgift.find_many(
            where={"createdAt": {"gte": today_start}}
        )
        gifts_count = len(gifts)

        return {
            "total_coins": total_coins,
            "mtd_revenue": mtd_revenue,
            "gifts_sent_today": gifts_count,
            "coins_trend": "+12% from last week",
            "revenue_trend": "+5.2% vs last month",
            "gifts_trend": f"+{gifts_count} vs yesterday"
        }
    except Exception as e:
        print(f"ECONOMY STATS ERROR: {str(e)}")
        return {
            "total_coins": 0,
            "mtd_revenue": 0,
            "gifts_sent_today": 0,
            "error": str(e)
        }


@router.get("/ledger/stats")
async def get_ledger_stats():
    try:
        payments = await db.payment.find_many(where={"status": "SUCCESSFUL"})
        total_gross = sum(p.amount for p in payments)
        total_net = sum(p.netAmount if p.netAmount else p.amount * 0.85 for p in payments)
        total_deductions = total_gross - total_net

        return {
            "total_gross": total_gross,
            "total_net": total_net,
            "total_deductions": total_deductions,
            "gross_trend": "+12%",
            "deductions_trend": "-2%"
        }
    except Exception as e:
        return {"error": str(e), "total_gross": 0, "total_net": 0, "total_deductions": 0}


# ---------------------------------------------------------------------------
# VIRTUAL ITEMS
# ---------------------------------------------------------------------------

@router.get("/items")
async def get_items():
    return await db.virtualitem.find_many(order={"createdAt": "desc"})


@router.post("/items")
async def create_item(
    name: str = Form(...),
    type: str = Form(...),
    price: int = Form(...),
    file: UploadFile = File(...)
):
    file_ext = file.filename.split(".")[-1]
    file_name = f"{uuid4()}.{file_ext}"
    file_path = f"uploads/economy/{file_name}"
    os.makedirs("uploads/economy", exist_ok=True)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    image_url = f"/uploads/economy/{file_name}"

    item = await db.virtualitem.create(
        data={
            "name": name,
            "type": type,
            "price": price,
            "imageUrl": image_url
        }
    )
    return item


@router.delete("/items/{item_id}")
async def delete_item(item_id: int):
    await db.virtualitem.delete(where={"id": item_id})
    return {"message": "Item deleted"}


@router.patch("/items/{item_id}/toggle")
async def toggle_item_status(item_id: int):
    item = await db.virtualitem.find_unique(where={"id": item_id})
    if not item:
        raise HTTPException(status_code=404)
    return await db.virtualitem.update(
        where={"id": item_id},
        data={"isActive": not item.isActive}
    )


# ---------------------------------------------------------------------------
# COIN PACKAGES (admin CRUD — actual purchase happens via /iap/verify)
# ---------------------------------------------------------------------------

class PackageCreate(BaseModel):
    name: str
    coins: int
    price: float
    currency: Optional[str] = "USD"
    googleProductId: Optional[str] = None   # Google Play "Product ID" for this pack


@router.get("/packages")
async def get_packages():
    return await db.coinpackage.find_many(order={"createdAt": "desc"})


@router.post("/packages")
async def create_package(data: PackageCreate):
    google_id = data.googleProductId if data.googleProductId and data.googleProductId.strip() != "" else None

    package = await db.coinpackage.create(
        data={
            "name": data.name,
            "coins": data.coins,
            "price": data.price,
            "currency": data.currency,
            "googleProductId": google_id
        }
    )
    return package


@router.delete("/packages/{pkg_id}")
async def delete_package(pkg_id: int):
    await db.coinpackage.delete(where={"id": pkg_id})
    return {"message": "Package deleted"}


@router.patch("/packages/{pkg_id}/toggle")
async def toggle_package_status(pkg_id: int):
    pkg = await db.coinpackage.find_unique(where={"id": pkg_id})
    if not pkg:
        raise HTTPException(status_code=404)
    return await db.coinpackage.update(
        where={"id": pkg_id},
        data={"isActive": not pkg.isActive}
    )


# ---------------------------------------------------------------------------
# SUBSCRIPTION PLANS (admin CRUD — actual purchase happens via /iap/verify-subscription)
# ---------------------------------------------------------------------------

class FeatureCreate(BaseModel):
    name: str
    description: Optional[str] = None
    iconUrl: Optional[str] = None


class SubscriptionPlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    duration: str  # WEEKLY, MONTHLY, YEARLY
    durationValue: int = 1
    features: List[FeatureCreate] = []
    googleProductId: Optional[str] = None   # Google Play Subscription "Product ID"
    dailySwipes: int = 10


@router.get("/plans")
async def get_plans():
    return await db.subscriptionplan.find_many(
        include={"features": True},
        order={"createdAt": "desc"}
    )


@router.post("/plans")
async def create_plan(data: SubscriptionPlanCreate):
    google_id = data.googleProductId if data.googleProductId and data.googleProductId.strip() != "" else None

    plan = await db.subscriptionplan.create(
        data={
            "name": data.name,
            "description": data.description,
            "price": data.price,
            "duration": data.duration,
            "durationValue": data.durationValue,
            "googleProductId": google_id,
            "dailySwipes": data.dailySwipes,
            "features": {
                "create": [
                    {
                        "name": f.name,
                        "description": f.description,
                        "iconUrl": f.iconUrl
                    } for f in data.features
                ]
            }
        },
        include={"features": True}
    )
    return plan


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int):
    plan = await db.subscriptionplan.find_unique(
        where={"id": plan_id},
        include={"features": True}
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.put("/plans/{plan_id}")
async def update_plan(plan_id: int, data: SubscriptionPlanCreate):
    google_id = data.googleProductId if data.googleProductId and data.googleProductId.strip() != "" else None

    plan = await db.subscriptionplan.update(
        where={"id": plan_id},
        data={
            "name": data.name,
            "description": data.description,
            "price": data.price,
            "duration": data.duration,
            "durationValue": data.durationValue,
            "googleProductId": google_id,
            "dailySwipes": data.dailySwipes
        }
    )

    await db.planfeature.delete_many(where={"planId": plan_id})

    if data.features:
        await db.planfeature.create_many(
            data=[
                {
                    "planId": plan_id,
                    "name": f.name,
                    "description": f.description,
                    "iconUrl": f.iconUrl
                } for f in data.features
            ]
        )

    return await db.subscriptionplan.find_unique(
        where={"id": plan_id},
        include={"features": True}
    )


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: int):
    try:
        plan = await db.subscriptionplan.find_unique(where={"id": plan_id})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if plan.name.lower() == "free":
            raise HTTPException(
                status_code=400,
                detail="The 'Free' plan is a system requirement and cannot be deleted. You can only edit its details or features."
            )

        active_users = await db.user.count(where={"tier": plan.name})
        if active_users > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete: {active_users} users are currently subscribed to {plan.name}. Please deactivate (Toggle) the plan instead to stop new signups."
            )

        await db.subscriptionplan.delete(where={"id": plan_id})
        return {"status": "success"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/plans/{plan_id}/toggle")
async def toggle_plan(plan_id: int):
    plan = await db.subscriptionplan.find_unique(where={"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    updated_plan = await db.subscriptionplan.update(
        where={"id": plan_id},
        data={"isActive": not plan.isActive}
    )
    return updated_plan


# ---------------------------------------------------------------------------
# GIFTING
# ---------------------------------------------------------------------------

class SendGiftRequest(BaseModel):
    sender_id: int
    receiver_id: int
    item_id: int


@router.post("/send-gift")
async def send_gift(data: SendGiftRequest):
    try:
        sender = await db.user.find_unique(where={"id": data.sender_id})
        item = await db.virtualitem.find_unique(where={"id": data.item_id})

        if not sender or not item:
            raise HTTPException(status_code=404, detail="User or Item not found")

        if sender.coins < item.price:
            raise HTTPException(status_code=400, detail="Insufficient coins")

        await db.user.update(
            where={"id": sender.id},
            data={"coins": {"decrement": item.price}}
        )

        await db.cointransaction.create(
            data={
                "userId": sender.id,
                "amount": -item.price,
                "type": "GIFT_SENT",
                "description": f"Sent {item.name} to user ID {data.receiver_id}"
            }
        )

        sent_gift = await db.sentgift.create(
            data={
                "senderId": data.sender_id,
                "receiverId": data.receiver_id,
                "itemId": data.item_id,
                "coinPrice": item.price
            }
        )

        return {
            "message": "Gift sent successfully",
            "sent_gift_id": sent_gift.id
        }

    except HTTPException as e:
        raise e

    except PrismaError as e:
        print("Prisma Error:", str(e))
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")

    except Exception as e:
        print("Unexpected Error:", str(e))
        raise HTTPException(status_code=500, detail=f"Unexpected Error: {str(e)}")


# ---------------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------------

@router.get("/transactions")
async def get_transactions():
    try:
        payments = await db.payment.find_many(
            include={"user": True},
            order={"createdAt": "desc"},
            take=50
        )
        return payments
    except Exception:
        return []


@router.get("/transactions/{user_id}")
async def get_user_transactions(user_id: int):
    return await db.cointransaction.find_many(
        where={"userId": user_id},
        order={"createdAt": "desc"}
    )
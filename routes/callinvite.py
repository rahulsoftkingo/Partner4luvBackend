"""
callinvite.py
--------------
Sends a high-priority, DATA-ONLY FCM push that triggers the receiver's
incoming-call screen.

DB-connected version — matches the existing Prisma schema where
User.id / Match.id / etc. are Int (autoincrement), not String.
"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from firebase_admin import messaging
from db import db

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class CallInviteRequest(BaseModel):
    targetUserId: int = Field(..., description="User ID of the call recipient")
    matchId: int = Field(..., description="Match ID linking caller and receiver")
    callType: Literal["video", "audio","text"] = Field(..., description="Type of call")
    senderId: int = Field(..., description="Caller's user ID")
    senderName: str = Field(..., description="Caller's display name")
    senderImage: Optional[str] = Field(None, description="Caller's avatar URL")


class CallInviteResponse(BaseModel):
    message: str
    fcmMessageId: str
    
class FcmTokenRequest(BaseModel):
    fcmToken: str


@router.post("/push/call-invite",response_model=CallInviteResponse,status_code=status.HTTP_200_OK,)
async def send_call_invite(payload: CallInviteRequest):

    # 1. Verify the match exists and the caller/receiver are actually part of it.
    match = await db.match.find_unique(where={"id": payload.matchId})
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found",
        )

    valid_pair = {match.user1Id, match.user2Id} == {payload.senderId, payload.targetUserId}
    if not valid_pair:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caller and receiver are not part of this match",
        )

    # 2. Look up the receiver and their FCM token
    receiver = await db.user.find_unique(where={"id": payload.targetUserId})
    if not receiver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receiver not found",
        )

    if not receiver.fcmToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Receiver has no registered device token",
        )

    # --- DEBUG: token clean + print karo, try/except se PEHLE ---
    clean_token = receiver.fcmToken.strip()
    print(f"RAW TOKEN: {receiver.fcmToken!r}")
    print(f"TOKEN LENGTH: {len(receiver.fcmToken)}")
    print(f"CLEAN TOKEN LENGTH: {len(clean_token)}")

    if not clean_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Receiver's FCM token is empty after cleanup",
        )

    # 3. Build message — agar callType "text" hai to notification field bhi add karo
    is_text = payload.callType == "text"

    message_kwargs = {
        "token": clean_token,
        "data": {
            "type": "TEXT_MESSAGE" if is_text else "CALL_INVITE",
            "callType": payload.callType,
            "matchId": str(payload.matchId),
            "senderId": str(payload.senderId),
            "senderName": payload.senderName,
            "senderImage": payload.senderImage or "",
        },
        "android": messaging.AndroidConfig(
            priority="high",
            ttl=30,
        ),
        "apns": messaging.APNSConfig(
            headers={
                "apns-priority": "10",
                "apns-push-type": "background" if not is_text else "alert",
            },
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    content_available=True,
                    sound="default" if is_text else None,
                ),
            ),
        ),
    }

    # Text message ke liye visible notification block add karo
    if is_text:
        message_kwargs["notification"] = messaging.Notification(
            title=payload.senderName,
            body="sent you a message",
        )

    message = messaging.Message(**message_kwargs)

    print("show printed error", message)

    # 4. Send via FCM
    try:
        fcm_message_id = messaging.send(message)
    except messaging.UnregisteredError as e:
        print(f"FCM UNREGISTERED TOKEN for user {receiver.id}: {e}")
        await db.user.update(
            where={"id": receiver.id},
            data={"fcmToken": None},
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Receiver's device token is no longer valid",
        )
    except Exception as e:
        print(f"FCM SEND ERROR: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"FCM send failed: {type(e).__name__}: {str(e)}",
        )

    # 5. Log the notification
    try:
        await db.notification.create(
            data={
                "message": f"{payload.senderName} sent you a message" if is_text else f"{payload.senderName} is calling you",
                "type": "TEXT_MESSAGE" if is_text else "CALL_INVITE",
                "status": "PENDING",
                "recipient": receiver.email,
                "userId": receiver.id,
            }
        )
    except Exception as e:
        print(f"NOTIFICATION LOG ERROR: {type(e).__name__}: {e}")

    return CallInviteResponse(
        message="Notification sent successfully",
        fcmMessageId=fcm_message_id,
    )

@router.post("/user/{user_id}/fcm-token")
async def update_fcm_token(user_id: int, payload: FcmTokenRequest):
    
    try:
        user = await db.user.find_unique(where={"id": user_id})
    except Exception as e:
        print(f"USER LOOKUP ERROR: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to look up user: {str(e)}")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    clean_token = payload.fcmToken.strip()
    if not clean_token:
        raise HTTPException(status_code=400, detail="FCM token cannot be empty")

    try:
        updated_user = await db.user.update(
            where={"id": user_id},
            data={"fcmToken": clean_token},
        )
    except Exception as e:
        print(f"FCM TOKEN UPDATE ERROR for user {user_id}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update FCM token: {str(e)}")

    return {
        "message": "FCM token updated successfully",
        "userId": user_id,
        "fcmToken": updated_user.fcmToken,
    }
# @router.post("/push/call-invite",response_model=CallInviteResponse,status_code=status.HTTP_200_OK,)
# async def send_call_invite(payload: CallInviteRequest):
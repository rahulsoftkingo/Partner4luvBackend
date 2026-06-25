# """
# callinvite.py
# --------------
# Sends a high-priority, DATA-ONLY FCM push that triggers the receiver's
# incoming-call screen.

# DB-connected version — matches the existing Prisma schema where
# User.id / Match.id / etc. are Int (autoincrement), not String.
# """

# from typing import Literal, Optional

# from fastapi import APIRouter, HTTPException, status
# from pydantic import BaseModel, Field
# from firebase_admin import messaging
# from db import db

# router = APIRouter()


# # ---------------------------------------------------------------------------
# # Request schema
# # ---------------------------------------------------------------------------

# class CallInviteRequest(BaseModel):
#     targetUserId: int = Field(..., description="User ID of the call recipient")
#     matchId: int = Field(..., description="Match ID linking caller and receiver")
#     callType: Literal["video", "audio"] = Field(..., description="Type of call")
#     senderId: int = Field(..., description="Caller's user ID")
#     senderName: str = Field(..., description="Caller's display name")
#     senderImage: Optional[str] = Field(None, description="Caller's avatar URL")


# class CallInviteResponse(BaseModel):
#     message: str
#     fcmMessageId: str


# # ---------------------------------------------------------------------------
# # Endpoint
# # ---------------------------------------------------------------------------

# @router.post(
#     "/push/call-invite",
#     response_model=CallInviteResponse,
#     status_code=status.HTTP_200_OK,
# )
# async def send_call_invite(payload: CallInviteRequest):

#     # 1. Verify the match exists and the caller/receiver are actually part of it.
#     #    (Prevents anyone from ringing a random user who isn't matched with them.)
#     match = await db.match.find_unique(where={"id": payload.matchId})
#     if not match:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Match not found",
#         )

#     valid_pair = {match.user1Id, match.user2Id} == {payload.senderId, payload.targetUserId}
#     if not valid_pair:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Caller and receiver are not part of this match",
#         )

#     # 2. Look up the receiver and their FCM token
#     receiver = await db.user.find_unique(where={"id": payload.targetUserId})
#     if not receiver:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Receiver not found",
#         )

#     if not receiver.fcmToken:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Receiver has no registered device token",
#         )

#     # 3. Build a DATA-ONLY message.
#     #    No "notification" key — this is what lets the receiving app wake up
#     #    and render its own full-screen incoming-call UI instead of a
#     #    default OS banner.
#     message = messaging.Message(
#         token=receiver.fcmToken,
#         data={
#             "type": "CALL_INVITE",
#             "callType": payload.callType,
#             "matchId": str(payload.matchId),
#             "senderId": str(payload.senderId),
#             "senderName": payload.senderName,
#             "senderImage": payload.senderImage or "",
#         },
#         android=messaging.AndroidConfig(
#             priority="high",
#             ttl=30,
#         ),
#         apns=messaging.APNSConfig(
#             headers={
#                 "apns-priority": "10",
#                 "apns-push-type": "background",
#             },
#             payload=messaging.APNSPayload(
#                 aps=messaging.Aps(content_available=True),
#             ),
#         ),
#     )

#     # 4. Send via FCM
#     try:
#         fcm_message_id = messaging.send(message)
#     except messaging.UnregisteredError:
#         # Token is dead — clear it so we stop trying to ring a dead device
#         await db.user.update(
#             where={"id": receiver.id},
#             data={"fcmToken": None},
#         )
#         raise HTTPException(
#             status_code=status.HTTP_410_GONE,
#             detail="Receiver's device token is no longer valid",
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_502_BAD_GATEWAY,
#             detail=f"FCM send failed: {str(e)}",
#         )

#     # 5. Log the call attempt using the existing Notification model
#     await db.notification.create(
#         data={
#             "message": f"{payload.senderName} is calling you",
#             "type": "CALL_INVITE",
#             "status": "PENDING",
#             "recipient": receiver.email,
#             "userId": receiver.id,
#         }
#     )

#     return CallInviteResponse(
#         message="Call invite sent successfully",
#         fcmMessageId=fcm_message_id,
#     )
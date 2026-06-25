from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from db import db
from datetime import datetime, timezone
import os
import uuid
from fastapi import UploadFile
# import whisper
import os


# model = whisper.load_model("base")
router = APIRouter(prefix="/chat", tags=["chat"])

class MessageSendRequest(BaseModel):
    matchId: int
    senderId: int
    content: str
    type: Optional[str] = "TEXT" # TEXT, IMAGE, GIFT

@router.on_event("startup")
async def startup():
    if not db.is_connected():
        await db.connect()

@router.get("/conversations/{user_id}")
async def get_conversations(user_id: int):
    # Find all matches for the user
    matches = await db.match.find_many(
        where={
            "OR": [
                {"user1Id": user_id},
                {"user2Id": user_id}
            ],
            "status": "ACTIVE"
        },
        include={
            "user1": {"include": {"profile": True, "photos": True}},
            "user2": {"include": {"profile": True, "photos": True}},
            "conversation": {
                "include": {
                    "messages": {
                        "order_by": {"createdAt": "desc"},
                        "take": 1
                    }
                }
            }
        }
    )

    result = []
    for m in matches:
        other_user = m.user2 if m.user1Id == user_id else m.user1
        last_message = None
        unread_count = 0
        
        if m.conversation:
            # Get last message
            if m.conversation.messages:
                last_message = m.conversation.messages[0]
            
            # Count unread messages (sent by OTHER user)
            unread_count = await db.message.count(
                where={
                    "conversationId": m.conversation.id,
                    "senderId": other_user.id,
                    "isRead": False
                }
            )
        
        result.append({
            "matchId": m.id,
            "otherUser": other_user,
            "lastMessage": last_message,
            "unreadCount": unread_count,
            "updatedAt": m.conversation.updatedAt if m.conversation else m.createdAt
        })
    
    # Sort by recent message/activity
    result.sort(key=lambda x: x["updatedAt"], reverse=True)
    return {"conversations": result}

@router.get("/messages/{match_id}")
async def get_messages(match_id: int, my_id: int, skip: int = 0, take: int = 50):
    
    # 1. Ensure conversation exists
    match = await db.match.find_unique(
        where={"id": match_id},
        include={"conversation": True}
    )
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if not match.conversation:
        return {status:200,"messages": []}

    # 2. Mark messages as read (those sent by the other person)
    await db.message.update_many(
        where={
            "conversationId": match.conversation.id,
            "senderId": {"not": my_id},
            "isRead": False
        },
        data={"isRead": True}
    )

    messages = await db.message.find_many(
        where={"conversationId": match.conversation.id},
        order={"createdAt": "desc"},
        skip=skip,
        take=take,
        include={"sender": True}
    )
    
    return {"messages": messages[::-1]} # Return in chronological order

@router.post("/messages/send")
async def send_message(data: MessageSendRequest):
    # 1. Get or Create Conversation for this Match
    match = await db.match.find_unique(
        where={"id": data.matchId},
        include={"conversation": True}
    )
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if not match.conversation:
        convo = await db.conversation.create(
            data={
                "matchId": data.matchId
            }
        )
        convo_id = convo.id
    else:
        convo_id = match.conversation.id

    # 2. Create Message
    message = await db.message.create(
        data={
            "conversationId": convo_id,
            "senderId": data.senderId,
            "content": data.content,
            "type": data.type
        }
    )
    
    # 3. Update Conversation updatedAt
    await db.conversation.update(
        where={"id": convo_id},
        data={"updatedAt": datetime.now(timezone.utc)}
    )
    
    return {"message": "Message sent", "data": message}


@router.delete("/conversations/clear/{user_id}")
async def clear_chat(user_id: int):
    try:
        # Mark messages as deleted for this user
        updated_messages = await db.message.update_many(
            where={"senderId": user_id},
            data={"isDelete": True}
        )

        return {
            "status":200,
            "message": "Chat cleared successfully",
        }

    except HTTPException:
        raise
    
    except Exception as e:
        raise HTTPException(status_code=500,detail=f"Failed to clear chat: {str(e)}")



# @router.post("/upload/audio")
# async def upload_audio(file: UploadFile):
#     contents = await file.read()

#     filename = f"{uuid.uuid4()}.mp3"
#     file_path = f"uploads/audio/{filename}"

#     os.makedirs(os.path.dirname(file_path), exist_ok=True)

#     with open(file_path, "wb") as f:
#         f.write(contents)

#     # Audio to Text
#     # result = model.transcribe(file_path)

#     return {
#         "audio_url": f"/uploads/audio/{filename}",
#         "text": result["text"]
#     }
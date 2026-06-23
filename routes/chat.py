from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from db import db
from datetime import datetime, timezone
import os
import uuid
from fastapi import UploadFile

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


@router.post("/upload/audio")
async def upload_audio(file: UploadFile):
    try:
        # Validate file type
        allowed_types = {"audio/mpeg", "audio/mp4", "audio/webm", "audio/ogg", "audio/wav"}
        if file.content_type not in allowed_types:
            raise HTTPException(400, "Unsupported audio format")

        # Validate size (e.g. max 10MB for voice notes)
        contents = await file.read()
        if len(contents) > 10 * 1024 * 1024:
            raise HTTPException(400, "File too large")

        if len(contents) == 0:
            raise HTTPException(400, "Empty file")

        # Save (local disk / S3 / cloud storage — adjust to your setup)
        ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
        filename = f"{uuid.uuid4()}.{ext}"
        file_path = f"uploads/audio/{filename}"

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(contents)
        except OSError as e:
            print(f"AUDIO UPLOAD WRITE ERROR: {e}")
            raise HTTPException(500, "Failed to save audio file")

        audio_url = f"/uploads/audio/{filename}"  # or your CDN/S3 URL
        return {"url": audio_url}

    except HTTPException:
        # re-raise as-is, already has proper status code + message
        raise
    except Exception as e:
        print(f"AUDIO UPLOAD ERROR: {e}")
        raise HTTPException(500, "Something went wrong while uploading audio")
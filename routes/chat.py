from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from db import db
from datetime import datetime, timezone
import os
import uuid
from fastapi import UploadFile
import asyncio
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
    # 1. Matches fetch karo sahi 'order_by' syntax ke saath
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
                        # FIX: Prisma Python Client mein nested relation ke liye 'order_by' aise likhte hain
                        "order_by": {
                            "createdAt": "desc"
                        },
                        "take": 1
                    }
                }
            }
        }
    )

    # 2. Results array aur background parallel tasks setup
    tasks = []
    temp_results = []

    for m in matches:
        other_user = m.user2 if m.user1Id == user_id else m.user1
        last_message = None
        
        if m.conversation and m.conversation.messages:
            last_message = m.conversation.messages[0]
        
        temp_results.append({
            "matchId": m.id,
            "otherUser": other_user,
            "lastMessage": last_message,
            "updatedAt": m.conversation.updatedAt if m.conversation else m.createdAt,
            "conversation_id": m.conversation.id if m.conversation else None
        })

        # Count queries ko parallel chalane ke liye list mein daalo
        if m.conversation:
            task = db.message.count(
                where={
                    "conversationId": m.conversation.id,
                    "senderId": other_user.id,
                    "isRead": False
                }
            )
            tasks.append(task)
        else:
            tasks.append(None)

    # 3. Parallel execution (Fast fetch logic)
    unread_counts = []
    if tasks:
        valid_tasks = [t for t in tasks if t is not None]
        if valid_tasks:
            valid_counts = await asyncio.gather(*valid_tasks)
            count_iter = iter(valid_counts)
            unread_counts = [next(count_iter) if t is not None else 0 for t in tasks]
        else:
            unread_counts = [0] * len(temp_results)
    else:
        unread_counts = [0] * len(temp_results)

    # 4. Final output array construct karo
    result = []
    for index, temp in enumerate(temp_results):
        result.append({
            "matchId": temp["matchId"],
            "otherUser": temp["otherUser"],
            "lastMessage": temp["lastMessage"],
            "unreadCount": unread_counts[index],
            "updatedAt": temp["updatedAt"]
        })
    
    # Sorting according to recent messages
    result.sort(key=lambda x: x["updatedAt"], reverse=True)
    
    # 5. Exact same JSON format return hoga
    return {"conversations": result}


@router.get("/messages/{match_id}")
async def get_messages(match_id: int, my_id: int, skip: int = 0, take: int = 50):
    
    # 1. Fetch only the conversation ID (Lightweight query)
    match = await db.match.find_unique(
        where={"id": match_id},
        include={"conversation": True}
    )
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if not match.conversation:
        return {"status": 200, "messages": []}

    conversation_id = match.conversation.id

    # 2. FIX: Fetch messages FIRST, don't make the user wait for the update
    messages = await db.message.find_many(
        where={"conversationId": conversation_id},
        order={"createdAt": "desc"},
        skip=skip,
        take=take,
        include={"sender": True}
    )


    async def mark_as_read_background():
        try:
            await db.message.update_many(
                where={
                    "conversationId": conversation_id,
                    "senderId": {"not": my_id},
                    "isRead": False
                },
                data={"isRead": True}
            )
        except Exception as e:
            # Log the error here if needed, but don't crash the user's request
            pass

    asyncio.create_task(mark_as_read_background())
    
    # 4. Return the messages instantly
    return {"messages": messages[::-1]}

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
from fastapi import APIRouter, HTTPException
from prisma.errors import PrismaError
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
router = APIRouter(prefix="/chat", tags=["chats"])

async def fetch_likes_received(
    user_id: int,
    limit: int = 20,
    offset: int = 0,
):
    """
    Returns profiles of users who liked/superliked `user_id`
    and have not yet received any response from `user_id`.
    """

    # 1. Validate user exists
    try:
        user = await db.user.find_unique(
            where={"id": user_id}
        )
    except PrismaError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user: {str(e)}"
        )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # 2. Users already responded to
    try:
        already_responded = await db.interaction.find_many(
            where={"fromUserId": user_id}
        )
    except PrismaError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching existing interactions: {str(e)}"
        )

    responded_ids = [row.toUserId for row in already_responded]

    # 3. Fetch pending likes
    try:
        pending_likes = await db.interaction.find_many(
            where={
                "toUserId": user_id,
                "type": {
                    "in": ["LIKE", "SUPERLIKE"]
                },
                "fromUserId": {
                    "notIn": responded_ids
                } if responded_ids else {},
            },
            order={"createdAt": "desc"},
            take=limit,
            skip=offset,
            include={
                "fromUser": True,
                "quote": True,
                "photo": True,
            },
        )
    except PrismaError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching pending likes: {str(e)}"
        )

    # 4. Build response
    results = []

    for interaction in pending_likes:
        liker = interaction.fromUser

        if not liker:
            continue

        results.append({
            "userId": liker.id,
            "name": liker.name,
            "photos": liker.photos,
            # "bio": liker.bio,

            "interactionType": interaction.type,
            "compliment": interaction.compliment,

            "quoteid": interaction.quoteid,
            "quote": {
                "id": interaction.quote.id,
                "text": interaction.quote.text
            } if interaction.quote else None,

            "photoId": interaction.photoId,
            "photo": {
                "id": interaction.photo.id,
                "url": interaction.photo.url
            } if interaction.photo else None,

            "likedAt": interaction.createdAt,
        })

    return {
        "count": len(results),
        "limit": limit,
        "offset": offset,
        "likes": results,
    }
        
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
async def get_detail_conversation_of_all_user(user_id: int):
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
    
    # Fetch pending likes
    likes_received = await fetch_likes_received(
        user_id=user_id,
        limit=20,
        offset=0,
    )
    
    # 5. Exact same JSON format return hoga
    return {"conversations": result, "likesReceived": likes_received}


@router.get("/messages/{match_id}")
async def get_messages(match_id: int,my_id: int,skip: int = 0,take: int = 50):
    # Fetch match with conversation
    match = await db.match.find_unique(
        where={"id": match_id},
        include={"conversation": True},
    )

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if not match.conversation:
        return {
            "messages": [],
            "likesReceived": await fetch_likes_received(my_id)
        }

    conversation_id = match.conversation.id

    # Fetch messages
    messages = await db.message.find_many(
        where={"conversationId": conversation_id},
        order={"createdAt": "desc"},
        skip=skip,
        take=take,
        include={"sender": True},
    )

    # Mark messages as read in background
    async def mark_as_read_background():
        try:
            await db.message.update_many(
                where={
                    "conversationId": conversation_id,
                    "senderId": {"not": my_id},
                    "isRead": False,
                },
                data={"isRead": True},
            )
        except Exception:
            pass

    asyncio.create_task(mark_as_read_background())

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
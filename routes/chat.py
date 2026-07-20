from fastapi import APIRouter, HTTPException, UploadFile, File, status
from prisma.errors import PrismaError
from typing import Optional
from pydantic import BaseModel
from db import db
from datetime import datetime, timezone
import os
import uuid
from fastapi import UploadFile
import asyncio
import traceback
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

    # 1b. Is user ne kin conversations ko clear kiya hai, sab ek saath fetch karo
    conversation_ids = [m.conversation.id for m in matches if m.conversation]

    clear_map = {}
    if conversation_ids:
        clear_records = await db.conversationclear.find_many(
            where={
                "userId": user_id,
                "conversationId": {"in": conversation_ids}
            }
        )
        clear_map = {c.conversationId: c.clearedAt for c in clear_records}

    # 2. Results array aur background parallel tasks setup
    tasks = []
    temp_results = []

    for m in matches:
        other_user = m.user2 if m.user1Id == user_id else m.user1
        last_message = None
        conversation_updated_at = m.conversation.updatedAt if m.conversation else m.createdAt

        cleared_at = clear_map.get(m.conversation.id) if m.conversation else None

        if m.conversation and m.conversation.messages:
            candidate = m.conversation.messages[0]
            # Sirf tab dikhao jab message clearedAt ke baad ka ho
            if not cleared_at or candidate.createdAt > cleared_at:
                last_message = candidate

        # Agar chat clear ho chuki hai aur uske baad koi naya message nahi aaya,
        # to updatedAt bhi clearedAt hi treat karo (list ko neeche push karne ke liye)
        if cleared_at and (not last_message):
            conversation_updated_at = cleared_at

        temp_results.append({
            "matchId": m.id,
            "otherUser": other_user,
            "lastMessage": last_message,
            "updatedAt": conversation_updated_at,
            "conversation_id": m.conversation.id if m.conversation else None,
        })

        # Count queries ko parallel chalane ke liye list mein daalo
        if m.conversation:
            unread_where = {
                "conversationId": m.conversation.id,
                "senderId": other_user.id,
                "isRead": False
            }
            # Cleared se pehle ke unread messages count mat karo
            if cleared_at:
                unread_where["createdAt"] = {"gt": cleared_at}

            task = db.message.count(where=unread_where)
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
   # Check karo agar is user ne ye chat clear ki hai
    clear_record = await db.conversationclear.find_unique(
        where={
            "conversationId_userId": {
                "conversationId": conversation_id,
                "userId": my_id
            }
        }
    )

    where_clause = {"conversationId": conversation_id}
    if clear_record:
        where_clause["createdAt"] = {"gt": clear_record.clearedAt}

    # Fetch messages
    messages = await db.message.find_many(
        where=where_clause,
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


class ClearChatRequest(BaseModel):
    matchId: int
    userId: int

@router.delete("/conversations/clear")
async def clear_chat(data: ClearChatRequest):
    try:
        match = await db.match.find_unique(
            where={"id": data.matchId},
            include={"conversation": True}
        )

        if not match:
            raise HTTPException(status_code=404, detail="Match not found")

        if not match.conversation:
            return {"status": 200, "message": "No conversation to clear"}

        conversation_id = match.conversation.id

        await db.conversationclear.upsert(
            where={
                "conversationId_userId": {
                    "conversationId": conversation_id,
                    "userId": data.userId
                }
            },
            data={
                "create": {
                    "conversationId": conversation_id,
                    "userId": data.userId,
                    "clearedAt": datetime.now(timezone.utc)
                },
                "update": {
                    "clearedAt": datetime.now(timezone.utc)
                }
            }
        )

        return {"status": 200, "message": "Chat cleared successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear chat: {str(e)}")

@router.post("/upload/audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        # Check if file is provided
        if file is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No audio file received."
            )

        # Check file name
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file."
            )

        # Create uploads folder if not exists
        upload_dir = "uploads/audio"
        os.makedirs(upload_dir, exist_ok=True)

        # Get extension from original file
        ext = os.path.splitext(file.filename)[1]
        if not ext:
            ext = ".mp3"

        filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(upload_dir, filename)

        # Read uploaded file
        contents = await file.read()

        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty."
            )

        # Save file
        with open(file_path, "wb") as f:
            f.write(contents)

        return {
            "success": True,
            "message": "Audio uploaded successfully.",
            "audio_url": f"/uploads/audio/{filename}"
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Audio Upload Error:")
        traceback.print_exc()  # Full error in terminal

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload audio: {str(e)}"
        )
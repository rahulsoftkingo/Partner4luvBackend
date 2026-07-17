import asyncio
from fastapi import APIRouter, HTTPException, status
from typing import Optional
from pydantic import BaseModel
from db import db
from datetime import datetime, timezone
import os
import time
from agora_token_builder import RtcTokenBuilder
from prisma.errors import ForeignKeyViolationError, UniqueViolationError, PrismaError

from db import db

router = APIRouter(prefix="/social", tags=["Social"])

class InteractionRequest(BaseModel):
    fromUserId: int
    toUserId: int
    compliment:str
    type: str # LIKE, SUPERLIKE, DISLIKE
    quoteid: Optional[int] = None
    photoid: Optional[int] = None
    
class UninteractRequest(BaseModel):
    fromUserId: int
    toUserId: int
    
class ChatThemeRequest(BaseModel):
    fromUserId: int
    matchId: int
    theme: str  
    
THEME_IMAGE_MAP = {
    "BLUE": "/uploads/themes/blue.jpg",
    "RED" : "/uploads/themes/red.jpg",
    "GREEN": "/uploads/themes/green.jpg"
}

ALLOWED_THEMES = set(THEME_IMAGE_MAP.keys())


@router.on_event("startup")
async def startup():
    if not db.is_connected():
        await db.connect()


@router.post("/interact")
async def interact(data: InteractionRequest):
    if data.fromUserId == data.toUserId:
        raise HTTPException(
            status_code=400,
            detail="Cannot interact with yourself"
        )

    # 1. Enforce Swipe Limits based on User's Persistent Limit
    try:
        user = await db.user.find_unique(
            where={"id": data.fromUserId}
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching user: {str(e)}")

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # Use stored swipe limit or default
    limit = user.swipeLimit if user.swipeLimit is not None else 10

    # Count today's likes/superlikes
    today = datetime.now(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    try:
        swipe_count = await db.interaction.count(
            where={
                "fromUserId": data.fromUserId,
                "type": {"in": ["LIKE", "SUPERLIKE"]},
                "createdAt": {"gte": today}
            }
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error counting swipes: {str(e)}")

    if swipe_count >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"Daily swipe limit reached ({limit}). Upgrade to Premium for unlimited swipes!"
        )

    # 2. Save or Update Interaction
    try:
        interaction = await db.interaction.upsert(
            where={
                "fromUserId_toUserId": {
                    "fromUserId": data.fromUserId,
                    "toUserId": data.toUserId
                }
            },
            data={
                "create": {
                    "fromUserId": data.fromUserId,
                    "toUserId": data.toUserId,
                    "type": data.type,
                    "compliment": data.compliment,
                    "quoteid": data.quoteid,
                    "photoId": data.photoid
                },
                "update": {
                    "type": data.type
                }
            }
        )
    except ForeignKeyViolationError as e:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid reference in interaction data "
                f"(check photoId='{data.photoid}', fromUserId='{data.fromUserId}', "
                f"toUserId='{data.toUserId}'): {str(e)}"
            )
        )
    except UniqueViolationError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate interaction conflict: {str(e)}"
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Database error saving interaction: {str(e)}")

    # 3. Handle DISLIKE immediately
    if data.type == "DISLIKE":
        return {
            "message": "Interaction saved",
            "isMatch": False,
            "reason": "You disliked this profile"
        }

    # 4. Check reverse interaction for LIKE/SUPERLIKE
    try:
        reverse_interaction = await db.interaction.find_unique(
            where={
                "fromUserId_toUserId": {
                    "fromUserId": data.toUserId,
                    "toUserId": data.fromUserId
                }
            }
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error checking reverse interaction: {str(e)}")

    # No reverse interaction yet
    if not reverse_interaction:
        return {
            "message": "Interaction saved",
            "isMatch": False,
            "reason": "Waiting for the other user to like you back"
        }

    # Reverse interaction exists but is DISLIKE
    if reverse_interaction.type == "DISLIKE":
        return {
            "message": "Interaction saved",
            "isMatch": False,
            "reason": "The other user has not liked your profile"
        }

    # Mutual LIKE / SUPERLIKE => Match
    if reverse_interaction.type in ["LIKE", "SUPERLIKE"]:

        try:
            match = await db.match.upsert(
                where={
                    "user1Id_user2Id": {
                        "user1Id": min(
                            data.fromUserId,
                            data.toUserId
                        ),
                        "user2Id": max(
                            data.fromUserId,
                            data.toUserId
                        )
                    }
                },
                data={
                    "create": {
                        "user1Id": min(
                            data.fromUserId,
                            data.toUserId
                        ),
                        "user2Id": max(
                            data.fromUserId,
                            data.toUserId
                        ),
                        "status": "ACTIVE"
                    },
                    "update": {
                        "status": "ACTIVE"
                    }
                }
            )
        except PrismaError as e:
            raise HTTPException(status_code=500, detail=f"Error creating match: {str(e)}")

        # 5. Agar kisi bhi interaction ke sath compliment tha,
        # use conversation ke message ke roop mein save karo
        try:
            conversation = await db.conversation.find_unique(
                where={"matchId": match.id}
            )

            if not conversation:
                conversation = await db.conversation.create(
                    data={"matchId": match.id}
                )

            # Chronological order maintain karne ke liye:
            # jisne pehle interact kiya (reverse_interaction), uska compliment pehle jaayega
            compliments_to_save = []

            if reverse_interaction.compliment:
                compliments_to_save.append(
                    (reverse_interaction.fromUserId, reverse_interaction.compliment)
                )

            if interaction.compliment:
                compliments_to_save.append(
                    (interaction.fromUserId, interaction.compliment)
                )

            for sender_id, compliment_text in compliments_to_save:
                await db.message.create(
                    data={
                        "conversationId": conversation.id,
                        "senderId": sender_id,
                        "content": compliment_text,
                        "type": "TEXT"
                    }
                )

            if compliments_to_save:
                await db.conversation.update(
                    where={"id": conversation.id},
                    data={"updatedAt": datetime.now(timezone.utc)}
                )

        except PrismaError as e:
            # Match already ho chuka hai, isliye compliment-save fail hone se
            # match response fail nahi karna chahiye - sirf log karo
            print(f"Error saving compliment as message: {str(e)}")

        return {
            "message": "Interaction saved",
            "isMatch": True,
            "reason": "Both users liked each other",
            "matchId": match.id
        }
    
@router.get("/interests/{user_id}")
async def get_user_matches(user_id: int):
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
            "user2": {"include": {"profile": True, "photos": True}}
        }
    )
    
    # Format matches to return the OTHER user
    result = []
    for m in matches:
        other_user = m.user2 if m.user1Id == user_id else m.user1
        result.append({
            "matchId": m.id,
            "user": other_user,
            "matchedAt": m.createdAt
        })
        
    return {"matches": result}

@router.get("/matches/{user_id}")
async def get_user_matches(user_id: int):
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
            "user2": {"include": {"profile": True, "photos": True}}
        }
    )
    
    # Format matches to return the OTHER user
    result = []
    for m in matches:
        other_user = m.user2 if m.user1Id == user_id else m.user1
        result.append({
            "matchId": m.id,
            "user": other_user,
            "matchedAt": m.createdAt
        })
        
    return {"matches": result}

@router.delete("/messages/match/delete")
async def delete_messages_by_match(matchId: str):
    # 1. Find the match and its associated conversation
    match = await db.match.find_unique(
        where={"id": matchId},
        include={"conversation": True}
    )
    
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Match not found"
        )
    
    if not match.conversation:
        raise HTTPException(
            status_code=status.HTTP_444_NOT_FOUND, # Or 200 with a "No history to clear" message
            detail="No conversation history found for this match"
        )
    
    convo_id = match.conversation.id

    # 2. Delete all messages inside this conversation
    # delete_many returns the count of deleted rows
    deleted_meta = await db.message.delete_many(
        where={
            "conversationId": convo_id
        }
    )
    
    # 3. Reset or update the conversation's updatedAt timestamp
    await db.conversation.update(
        where={"id": convo_id},
        data={"updatedAt": datetime.now(timezone.utc)}
    )
    
    return {
        "message": "Chat history cleared successfully",
        "deleted_count": deleted_meta
    }


# @router.push("/push/notifications")
# async def delete_messages_by_match(matchId: str):
#     # 1. Find the match and its associated conversation
#     match = await db.match.find_unique(
#         where={"id": matchId},
#         include={"conversation": True}
#     )
    
#     if not match:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND, 
#             detail="Match not found"
#         )
    
#     if not match.conversation:
#         raise HTTPException(
#             status_code=status.HTTP_444_NOT_FOUND, # Or 200 with a "No history to clear" message
#             detail="No conversation history found for this match"
#         )
    
#     convo_id = match.conversation.id

#     # 2. Delete all messages inside this conversation
#     # delete_many returns the count of deleted rows
#     deleted_meta = await db.message.delete_many(
#         where={
#             "conversationId": convo_id
#         }
#     )
    
#     # 3. Reset or update the conversation's updatedAt timestamp
#     await db.conversation.update(
#         where={"id": convo_id},
#         data={"updatedAt": datetime.now(timezone.utc)}
#     )
    
#     return {
#         "message": "Chat history cleared successfully",
#         "deleted_count": deleted_meta
#     }

# @router.get("/recommendations/{user_id}")
# async def get_recommendations(user_id: int, skip: int = 0, take: int = 20):
    
#     # 1. FIX: 'select' hata kar 'include' lagaya taaki TypeError na aaye
#     user = await db.user.find_unique(
#         where={"id": user_id},
#         include={"profile": True}
#     )
    
#     if not user or not user.profile:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND, 
#             detail="User profile not completed"
#         )

#     # Prisma Python Client ke hisab se dot (.) notation use karenge
#     profile = user.profile
#     my_gender = getattr(profile, "gender", None)
#     interested_in = getattr(profile, "interestedIn", None)

#     # 2. Opposite Gender Logic
#     if not interested_in or len(interested_in) == 0:
#         if my_gender == "MALE":
#             interested_in = ["FEMALE"]
#         elif my_gender == "FEMALE":
#             interested_in = ["MALE"]
#         else:
#             interested_in = []

#     # Gender filter structure setup
#     gender_filter = {}
#     if interested_in:
#         gender_filter = {"gender": {"in": interested_in}}

#     # 3. Interacted users ki list fetch karo
#     interacted = await db.interaction.find_many(
#         where={"fromUserId": user_id}
#     )
    
#     interacted_ids = {i.toUserId for i in interacted if hasattr(i, 'toUserId')}
#     interacted_ids.add(user_id) 
#     interacted_list = list(interacted_ids)

#     # 4. Main Query Condition (Relation filtering without "is" keyword)
#     where_condition = {
#         "id": {"not_in": interacted_list},
#         "status": "ACTIVE"
#     }
    
#     if gender_filter:
#         where_condition["profile"] = gender_filter

#     # 5. Parallel Execution (Fast performance ke liye)
#     count_task = db.user.count(where=where_condition)
#     candidates_task = db.user.find_many(
#         where=where_condition,
#         include={
#             "profile": True,
#             "photos": {"take": 5},
#         },
#         skip=skip,
#         take=take
#     )

#     total_count, candidates = await asyncio.gather(count_task, candidates_task)

#     # 6. JSON output structure formatting
#     final_list = [{"user": cand} for cand in candidates]

#     return {
#         "recommendations": final_list,
#         "total": total_count
#     }


@router.get("/recommendations/{user_id}")
async def get_recommendations(
    user_id: int,
    skip: int = 0,
    take: int = 20,
    min_age: int | None = None,
    max_age: int | None = None,
    min_height: float | None = None,
    max_height: float | None = None,
    max_distance_km: float | None = None,
):

    # 1. fetch our user profile
    user = await db.user.find_unique(
        where={"id": user_id},
        include={"profile": True}
    )

    if not user or not user.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not completed"
        )

    profile = user.profile
    my_gender = getattr(profile, "gender", None)
    interested_in = getattr(profile, "interestedIn", None)
    my_lat = getattr(profile, "latitude", None)
    my_lng = getattr(profile, "longitude", None)

    # 2. Opposite Gender Logic
    if not interested_in or len(interested_in) == 0:
        if my_gender == "MALE":
            interested_in = ["FEMALE"]
        elif my_gender == "FEMALE":
            interested_in = ["MALE"]
        else:
            interested_in = []

    # 3. Interacted users ki list
    interacted = await db.interaction.find_many(
        where={"fromUserId": user_id}
    )
    interacted_ids = {i.toUserId for i in interacted if hasattr(i, 'toUserId')}
    interacted_ids.add(user_id)
    interacted_list = list(interacted_ids)

    # ============================================================
    # PATH A: Distance filter chahiye -> raw SQL (Haversine)
    # ============================================================
    if max_distance_km is not None and my_lat is not None and my_lng is not None:

        excluded = interacted_list or [0]
        excluded_sql = ",".join(str(i) for i in excluded)

        conditions = [f'u.id NOT IN ({excluded_sql})', 'u.status = \'ACTIVE\'']
        params = [my_lat, my_lng]  # $1 = my_lat, $2 = my_lng
        idx = 3

        gender_clause = ""
        if interested_in:
            gender_clause = f'AND p."gender" = ANY(${idx}::"Gender"[])'
            params.append(interested_in)
            idx += 1

        height_clause = ""
        if min_height is not None:
            height_clause += f' AND p."height" >= ${idx}'
            params.append(min_height)
            idx += 1
        if max_height is not None:
            height_clause += f' AND p."height" <= ${idx}'
            params.append(max_height)
            idx += 1

        age_clause = ""
        today = date.today()
        if max_age is not None:
            oldest_dob = today - timedelta(days=(max_age + 1) * 365.25)
            age_clause += f' AND p."dateOfBirth" >= ${idx}'
            params.append(oldest_dob)
            idx += 1
        if min_age is not None:
            youngest_dob = today - timedelta(days=min_age * 365.25)
            age_clause += f' AND p."dateOfBirth" <= ${idx}'
            params.append(youngest_dob)
            idx += 1

        distance_param_idx = idx
        params.append(max_distance_km)

        base_query = f"""
            FROM "User" u
            JOIN "Profile" p ON p."userId" = u.id
            WHERE u.id NOT IN ({excluded_sql})
              AND u.status = 'ACTIVE'
              {gender_clause}
              {height_clause}
              {age_clause}
              AND p.latitude IS NOT NULL
              AND p.longitude IS NOT NULL
              AND (6371 * acos(
                    cos(radians($1)) * cos(radians(p.latitude)) *
                    cos(radians(p.longitude) - radians($2)) +
                    sin(radians($1)) * sin(radians(p.latitude))
              )) <= ${distance_param_idx}
        """

        select_query = f"""
            SELECT u.id,
                (6371 * acos(
                    cos(radians($1)) * cos(radians(p.latitude)) *
                    cos(radians(p.longitude) - radians($2)) +
                    sin(radians($1)) * sin(radians(p.latitude))
                )) AS distance_km
            {base_query}
            ORDER BY distance_km ASC
            OFFSET {skip} LIMIT {take}
        """

        count_query = f"SELECT COUNT(*) AS count {base_query}"

        raw_results = await db.query_raw(select_query, *params)
        count_result = await db.query_raw(count_query, *params)

        total_count = count_result[0]["count"] if count_result else 0
        result_ids = [r["id"] for r in raw_results]
        distance_map = {r["id"]: r["distance_km"] for r in raw_results}

        if not result_ids:
            return {"recommendations": [], "total": total_count}

        candidates = await db.user.find_many(
            where={"id": {"in": result_ids}},
            include={"profile": True, "photos": {"take": 5}}
        )
        candidates.sort(key=lambda c: result_ids.index(c.id))

        final_list = [
            {
                "user": {
                    **cand.dict(),
                    "distance_km": round(distance_map[cand.id], 2)
                }
            }
            for cand in candidates
        ]

        return {"recommendations": final_list, "total": total_count}

    # ============================================================
    # PATH B: Distance filter nahi chahiye -> normal Prisma query
    # ============================================================
    profile_filter = {}
    if interested_in:
        profile_filter["gender"] = {"in": interested_in}

    height_condition = {}
    if min_height is not None:
        height_condition["gte"] = min_height
    if max_height is not None:
        height_condition["lte"] = max_height
    if height_condition:
        profile_filter["height"] = height_condition

    if min_age is not None or max_age is not None:
        today = date.today()
        dob_condition = {}
        if max_age is not None:
            oldest_dob = today - timedelta(days=(max_age + 1) * 365.25)
            dob_condition["gte"] = oldest_dob
        if min_age is not None:
            youngest_dob = today - timedelta(days=min_age * 365.25)
            dob_condition["lte"] = youngest_dob
        profile_filter["dateOfBirth"] = dob_condition

    where_condition = {
        "id": {"not_in": interacted_list},
        "status": "ACTIVE"
    }
    if profile_filter:
        where_condition["profile"] = profile_filter

    count_task = db.user.count(where=where_condition)
    candidates_task = db.user.find_many(
        where=where_condition,
        include={
            "profile": True,
            "photos": {"take": 5},
        },
        skip=skip,
        take=take
    )

    total_count, candidates = await asyncio.gather(count_task, candidates_task)

    final_list = [{"user": cand} for cand in candidates]

    return {
        "recommendations": final_list,
        "total": total_count
    }
    
"""
Agora Dynamic RTC Token Generator API
--------------------------------------
For production: generates a dynamic Agora RTC token for the current user
(caller) every time a call is initiated, and returns it to the client.

Install dependency (also add to production requirements.txt):
    pip install agora-token-builder

Environment variables required (.env / server config):
    AGORA_APP_ID          -> App ID from the Agora Console
    AGORA_APP_CERTIFICATE -> Primary Certificate from the Agora Console
                              (certificate must be enabled for dynamic
                              tokens to work)
"""


# ---------------------------------------------------------------------
# Config (comes from environment variables, never hardcode credentials)
# ---------------------------------------------------------------------
AGORA_APP_ID = os.getenv("AGORA_APP_ID")
AGORA_APP_CERTIFICATE = os.getenv("AGORA_APP_CERTIFICATE")

# How long the token stays valid, in seconds. Default: 1 hour.
DEFAULT_TOKEN_EXPIRY_SECONDS = 3600

# Agora roles
ROLE_PUBLISHER = 1  # broadcaster / can send + receive audio-video
ROLE_SUBSCRIBER = 2  # can only receive


class AgoraTokenRequest(BaseModel):
    fromUserId: int                     # current logged-in user (caller / joiner)
    matchId: int                        # the dating-app match this call is against (Match.id is Int in schema)
    channelName: Optional[str] = None   # optional override, otherwise derived from matchId


@router.on_event("startup")
async def startup():
    if not db.is_connected():
        await db.connect()


def _build_channel_name(match_id: int) -> str:
    # Both users (caller/callee) join this same channel name,
    # so it must be deterministic — derived from matchId.
    return f"match_{match_id}"



@router.post("/token")
async def generate_agora_token(data: AgoraTokenRequest):
    if not AGORA_APP_ID or not AGORA_APP_CERTIFICATE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agora credentials not configured on server"
        )

    # 1. Validate the user
    user = await db.user.find_unique(where={"id": data.fromUserId})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 2. Validate the match and confirm this user is actually part of it
    match = await db.match.find_unique(where={"id": data.matchId})
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found"
        )

    if data.fromUserId not in (match.user1Id, match.user2Id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not part of this match, cannot join call"
        )

    if match.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Match is not active, cannot start a call"
        )

    # 3. Decide the channel name (both users will meet on this same channel)
    channel_name = data.channelName or _build_channel_name(data.matchId)

    # 4. Calculate token expiry
    current_ts = int(time.time())
    privilege_expired_ts = current_ts + DEFAULT_TOKEN_EXPIRY_SECONDS

    # 5. Generate the Agora dynamic RTC token (uid = fromUserId)
    try:
        token = RtcTokenBuilder.buildTokenWithUid(
            AGORA_APP_ID,
            AGORA_APP_CERTIFICATE,
            channel_name,
            data.fromUserId,
            ROLE_PUBLISHER,
            privilege_expired_ts
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Agora token: {str(e)}"
        )

    return {
        "appId": AGORA_APP_ID,
        "channelName": channel_name,
        "uid": data.fromUserId,
        "token": token,
        "expiresAt": privilege_expired_ts,
        "role": "PUBLISHER"
    }



@router.post("/uninteract")
async def uninteract(data: UninteractRequest):
    if data.fromUserId == data.toUserId:
        raise HTTPException(status_code=400, detail="Cannot un-interact with yourself")

    try:
        interactions = await db.interaction.find_many(
            where={
                "OR": [
                    {"fromUserId": data.fromUserId, "toUserId": data.toUserId},
                    {"fromUserId": data.toUserId, "toUserId": data.fromUserId},
                ]
            }
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching interactions: {str(e)}")

    if not interactions:
        raise HTTPException(status_code=404, detail="No interaction found between these users")
    
    try:
        await db.interaction.delete_many(
            where={
                "OR": [
                    {"fromUserId": data.fromUserId, "toUserId": data.toUserId},
                    {"fromUserId": data.toUserId, "toUserId": data.fromUserId},
                ]
            }
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error deleting interactions: {str(e)}")

    match = await db.match.find_first(where={
        "user1Id": min(data.fromUserId, data.toUserId),
        "user2Id": max(data.fromUserId, data.toUserId),
    })

    match_unmatched = False
    if match:
        try:
            await db.match.update(
                where={"id": match.id},
                data={"status": "UNMATCHED"}
            )
            match_unmatched = True
        except PrismaError as e:
            raise HTTPException(status_code=500, detail=f"Error updating match status: {str(e)}")

    return {
        "status": "ok",
        "interactionsRemoved": len(interactions),
        "matchUnmatched": match_unmatched,
        "messagesPreserved": True
    }


@router.post("/chat-theme")
async def set_chat_theme(data: ChatThemeRequest):

    theme_normalized = data.theme.strip().upper()

    # Validate that the requested theme actually exists
    if theme_normalized not in ALLOWED_THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid theme. Allowed values: {', '.join(ALLOWED_THEMES)}"
        )

    # 1. Validate the match exists
    try:
        match = await db.match.find_unique(where={"id": data.matchId})
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching match: {str(e)}")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Make sure the requesting user is actually part of this match
    if data.fromUserId not in (match.user1Id, match.user2Id):
        raise HTTPException(
            status_code=403,
            detail="You are not part of this match"
        )

    if match.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Match is not active")

    # Identify the other user in this match
    other_user_id = match.user2Id if match.user1Id == data.fromUserId else match.user1Id

    # 2. Save or update this user's chosen theme for this match (upsert)
    try:
        my_theme = await db.chattheme.upsert(
            where={
                "matchId_userId": {
                    "matchId": data.matchId,
                    "userId": data.fromUserId
                }
            },
            data={
                "create": {
                    "matchId": data.matchId,
                    "userId": data.fromUserId,
                    "theme": theme_normalized
                },
                "update": {
                    "theme": theme_normalized
                }
            }
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error saving chat theme: {str(e)}")

    # 3. Check what theme the other user has selected (if any)
    try:
        other_theme = await db.chattheme.find_unique(
            where={
                "matchId_userId": {
                    "matchId": data.matchId,
                    "userId": other_user_id
                }
            }
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error checking other user's theme: {str(e)}")

    # 4. If both users picked the same theme -> trigger Super Match response
    if other_theme and other_theme.theme == theme_normalized:
        return {
            "message": "Both users chose the same vibe!",
            "isSuperMatch": True,
            "theme": theme_normalized,
            "imageUrl": THEME_IMAGE_MAP[theme_normalized],
            "matchId": data.matchId
        }

    # Otherwise, just confirm the theme was saved for this user only
    return {
        "message": "Chat theme updated",
        "isSuperMatch": False,
        "theme": theme_normalized,
        "imageUrl": THEME_IMAGE_MAP[theme_normalized],
        "matchId": data.matchId,
        "reason": "Waiting to see if the other user picks the same background"
    }

@router.get("/chat-theme/options/list")
async def get_available_themes():
    themes = [
        {"theme": theme_name, "imageUrl": image_url}
        for theme_name, image_url in THEME_IMAGE_MAP.items()
    ]

    return {
        "themes": themes
    }


@router.get("/chattheme/{match_id}")
async def get_chat_theme(match_id: str, userId: int):
    try:
        match = await db.match.find_unique(where={"id": match_id})
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching match: {str(e)}")
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    other_user_id = match.user2Id if match.user1Id == userId else match.user1Id
    try:
        my_theme = await db.chattheme.find_unique(
            where={"matchId_userId": {"matchId": match_id, "userId": userId}}
        )
        other_theme = await db.chattheme.find_unique(
            where={"matchId_userId": {"matchId": match_id, "userId": other_user_id}}
        )
    except PrismaError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching themes: {str(e)}")
    is_super_match = bool(
        my_theme and other_theme and my_theme.theme == other_theme.theme
    )
    return {
        "matchId": match_id,
        "myTheme": my_theme.theme if my_theme else None,
        "otherUserTheme": other_theme.theme if other_theme else None,
        "isSuperMatch": is_super_match
    }  
# @router.post("/token/subscribe")

# @router.get("/recommendations/{user_id}")
# async def get_recommendations(user_id: int, skip: int = 0, take: int = 20):
#     from datetime import datetime
#     import math

#     # 1. Get current user's profile and preferences
#     user = await db.user.find_unique(
#         where={"id": user_id},
#         include={"profile": True, "responses": {"include": {"option": True}}}
#     )
#     if not user or not user.profile:
#         raise HTTPException(status_code=404, detail="User profile not completed")

#     p = user.profile
#     user_tags = set()
#     for resp in user.responses:
#         # Safely get tags if they exist on the option object
#         tags = getattr(resp.option, "tags", None)
#         if tags:
#             user_tags.update(tags)
#     # 2. Exclude already interacted users
#     interacted = await db.interaction.find_many(where={"fromUserId": user_id})
#     interacted_ids = [i.toUserId for i in interacted]
#     interacted_ids.append(user_id)

#     # 3. Build Filters
#     # Filter by Gender (Interested In)
#     gender_filter = {}
#     if p.interestedIn and len(p.interestedIn) > 0:
#         gender_filter = {"gender": {"in": p.interestedIn}}

#     # Filter by Age Range
#     min_year = (datetime.now().year - p.maxAgePref) if p.maxAgePref else 1900
#     max_year = (datetime.now().year - p.minAgePref) if p.minAgePref else datetime.now().year
    
#     # Simple birthDate filter (assumes ISO string or DateTime)
#     # Since Prisma handles DateTime, we calculate bounds
#     age_filter = {}
#     if p.minAgePref or p.maxAgePref:
#         # Note: This is approximate by year
#         age_filter = {
#             "birthDate": {
#                 "gte": datetime(min_year, 1, 1),
#                 "lte": datetime(max_year, 12, 31)
#             }
#         }

#     # 4. Fetch Candidates
#     candidates = await db.user.find_many(
#         where={
#             "id": {"not_in": interacted_ids},
#             "status": "ACTIVE",
#             "profile": {
#                 "is": {
#                     **gender_filter,
#                     **age_filter
#                 }
#             }
#         },
#         include={
#             "profile": True, 
#             # "photos": {"where": {"aiStatus": "VERIFIED"}, "take": 5},
#             "photos": {"take": 5},
#             "responses": {"include": {"option": True}}
#         },
#         take=100
#     )
    
     
#     # recommendations = []

#     # for user in candidates:
#     #     recommendations.append({
#     #         "id": user.id,
#     #         "name": user.name,
#     #         "email": user.email,
#     #         "matchRate": user.matchRate,
#     #         "profile": {
#     #             "city": user.profile.city,
#     #             "country": user.profile.country,
#     #             "bio": user.profile.bio,
#     #             "gender": user.profile.gender,
#     #         }
#     #     })
#     # 5. Distance Calculation & Scoring
#     scored_candidates = []
    
#     def calculate_distance(lat1, lon1, lat2, lon2):
#         if not all([lat1, lon1, lat2, lon2]): return 9999
#         # Haversine formula
#         R = 6371 # Earth radius in km
#         dLat = math.radians(lat2 - lat1)
#         dLon = math.radians(lon2 - lon1)
#         a = math.sin(dLat/2) * math.sin(dLat/2) + \
#             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
#             math.sin(dLon/2) * math.sin(dLon/2)
#         c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
#         return R * c

#     for cand in candidates:
#         if not cand.profile: continue
        
#         print(f"Show latitude and longitude for p and cand {cand.profile.lat} - {cand.profile.lng}-{p.lat} - {p.lng}", end="\n")
#         # Distance Filter
#         dist = calculate_distance(p.lat, p.lng, cand.profile.lat, cand.profile.lng)
#         if p.maxDistance and dist > p.maxDistance:
#             continue

#         # Tag Scoring
#         cand_tags = set()
#         for resp in cand.responses:
#             if resp.option.tags: cand_tags.update(resp.option.tags)
        
#         tag_score = 0
#         if user_tags and cand_tags:
#             intersection = len(user_tags.intersection(cand_tags))
#             union = len(user_tags.union(cand_tags))
#             tag_score = (intersection / union) * 100 if union > 0 else 0
        
#         # Final Score: Weighting (Tags 70%, Distance 30%)
#         # Closer is better
#         dist_score = max(0, 100 - (dist / (p.maxDistance or 50) * 100)) if dist != 9999 else 0
#         final_score = (tag_score * 0.7) + (dist_score * 0.3)

#         scored_candidates.append({
#             "user": cand,
#             "matchScore": round(final_score, 1),
#             "distance": round(dist, 1) if dist != 9999 else None,
#             "isBlurred": user.tier == "Free"
#         })

#     # 6. Sort and Obfuscate
#     scored_candidates.sort(key=lambda x: x["matchScore"], reverse=True)
    
#     final_list = scored_candidates[skip:skip+take]
#     if user.tier == "Free":
#         for item in final_list:
#             item["user"].profile.bio = "Upgrade to Premium to see bio"
#             item["user"].profile.promptHopingYou = "*** Hidden ***"
#             item["user"].profile.promptHeartWay = "*** Hidden ***"
    
#     return {
#         "recommendations": final_list,
#         "total": len(scored_candidates),
#         "userTier": user.tier
#     }

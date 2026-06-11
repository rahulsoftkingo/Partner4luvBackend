from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from db import db
from datetime import datetime, timezone

router = APIRouter(prefix="/social", tags=["social"])

class InteractionRequest(BaseModel):
    fromUserId: int
    toUserId: int
    type: str # LIKE, SUPERLIKE, DISLIKE

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
    user = await db.user.find_unique(
        where={"id": data.fromUserId}
    )

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

    swipe_count = await db.interaction.count(
        where={
            "fromUserId": data.fromUserId,
            "type": {"in": ["LIKE", "SUPERLIKE"]},
            "createdAt": {"gte": today}
        }
    )

    if swipe_count >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"Daily swipe limit reached ({limit}). Upgrade to Premium for unlimited swipes!"
        )

    # 2. Save or Update Interaction
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
                "type": data.type
            },
            "update": {
                "type": data.type
            }
        }
    )

    # 3. Handle DISLIKE immediately
    if data.type == "DISLIKE":
        return {
            "message": "Interaction saved",
            "isMatch": False,
            "reason": "You disliked this profile"
        }

    # 4. Check reverse interaction for LIKE/SUPERLIKE
    reverse_interaction = await db.interaction.find_unique(
        where={
            "fromUserId_toUserId": {
                "fromUserId": data.toUserId,
                "toUserId": data.fromUserId
            }
        }
    )

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

        return {
            "message": "Interaction saved",
            "isMatch": True,
            "reason": "Both users liked each other",
            "matchId": match.id
        }

    # Fallback
    return {
        "message": "Interaction saved",
        "isMatch": False,
        "reason": "Match conditions not satisfied"
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

@router.get("/recommendations/{user_id}")
async def get_recommendations(user_id: int, skip: int = 0, take: int = 20):
    from datetime import datetime
    import math

    # 1. Get current user's profile and preferences
    user = await db.user.find_unique(
        where={"id": user_id},
        include={"profile": True, "responses": {"include": {"option": True}}}
    )
    if not user or not user.profile:
        raise HTTPException(status_code=404, detail="User profile not completed")

    p = user.profile
    user_tags = set()
    for resp in user.responses:
        # Safely get tags if they exist on the option object
        tags = getattr(resp.option, "tags", None)
        if tags:
            user_tags.update(tags)
    # 2. Exclude already interacted users
    interacted = await db.interaction.find_many(where={"fromUserId": user_id})
    interacted_ids = [i.toUserId for i in interacted]
    interacted_ids.append(user_id)

    # 3. Build Filters
    # Filter by Gender (Interested In)
    gender_filter = {}
    if p.interestedIn and len(p.interestedIn) > 0:
        gender_filter = {"gender": {"in": p.interestedIn}}

    # Filter by Age Range
    min_year = (datetime.now().year - p.maxAgePref) if p.maxAgePref else 1900
    max_year = (datetime.now().year - p.minAgePref) if p.minAgePref else datetime.now().year
    
    # Simple birthDate filter (assumes ISO string or DateTime)
    # Since Prisma handles DateTime, we calculate bounds
    age_filter = {}
    if p.minAgePref or p.maxAgePref:
        # Note: This is approximate by year
        age_filter = {
            "birthDate": {
                "gte": datetime(min_year, 1, 1),
                "lte": datetime(max_year, 12, 31)
            }
        }

    # 4. Fetch Candidates
    candidates = await db.user.find_many(
        where={
            "id": {"not_in": interacted_ids},
            "status": "ACTIVE",
            "profile": {
                "is": {
                    **gender_filter,
                    **age_filter
                }
            }
        },
        include={
            "profile": True, 
            # "photos": {"where": {"aiStatus": "VERIFIED"}, "take": 5},
            "photos": {"take": 5},
            "responses": {"include": {"option": True}}
        },
        take=100
    )
    
     
    # recommendations = []

    # for user in candidates:
    #     recommendations.append({
    #         "id": user.id,
    #         "name": user.name,
    #         "email": user.email,
    #         "matchRate": user.matchRate,
    #         "profile": {
    #             "city": user.profile.city,
    #             "country": user.profile.country,
    #             "bio": user.profile.bio,
    #             "gender": user.profile.gender,
    #         }
    #     })
    # 5. Distance Calculation & Scoring
    scored_candidates = []
    
    def calculate_distance(lat1, lon1, lat2, lon2):
        if not all([lat1, lon1, lat2, lon2]): return 9999
        # Haversine formula
        R = 6371 # Earth radius in km
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        a = math.sin(dLat/2) * math.sin(dLat/2) + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(dLon/2) * math.sin(dLon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    for cand in candidates:
        if not cand.profile: continue
        
        print(f"Show latitude and longitude for p and cand {cand.profile.lat} - {cand.profile.lng}-{p.lat} - {p.lng}", end="\n")
        # Distance Filter
        dist = calculate_distance(p.lat, p.lng, cand.profile.lat, cand.profile.lng)
        if p.maxDistance and dist > p.maxDistance:
            continue

        # Tag Scoring
        cand_tags = set()
        for resp in cand.responses:
            if resp.option.tags: cand_tags.update(resp.option.tags)
        
        tag_score = 0
        if user_tags and cand_tags:
            intersection = len(user_tags.intersection(cand_tags))
            union = len(user_tags.union(cand_tags))
            tag_score = (intersection / union) * 100 if union > 0 else 0
        
        # Final Score: Weighting (Tags 70%, Distance 30%)
        # Closer is better
        dist_score = max(0, 100 - (dist / (p.maxDistance or 50) * 100)) if dist != 9999 else 0
        final_score = (tag_score * 0.7) + (dist_score * 0.3)

        scored_candidates.append({
            "user": cand,
            "matchScore": round(final_score, 1),
            "distance": round(dist, 1) if dist != 9999 else None,
            "isBlurred": user.tier == "Free"
        })

    # 6. Sort and Obfuscate
    scored_candidates.sort(key=lambda x: x["matchScore"], reverse=True)
    
    final_list = scored_candidates[skip:skip+take]
    if user.tier == "Free":
        for item in final_list:
            item["user"].profile.bio = "Upgrade to Premium to see bio"
            item["user"].profile.promptHopingYou = "*** Hidden ***"
            item["user"].profile.promptHeartWay = "*** Hidden ***"
    
    return {
        "recommendations": final_list,
        "total": len(scored_candidates),
        "userTier": user.tier
    }

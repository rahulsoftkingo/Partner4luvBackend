from fastapi import APIRouter, HTTPException
from db import db
from ai_utils import ai_client
from ai_insights import generate_match_insight,bio_generation,analyze_personality
from typing import Optional
from pydantic import BaseModel

class BioRequest(BaseModel):
    text: str
    
router = APIRouter(tags=["ai"])

@router.on_event("startup")
async def startup():
    if not db.is_connected():
        await db.connect()

@router.get("/ai/test")
async def test_ai():
    return {"status": "AI Route works"}

@router.post("/ai/verify-profile/{user_id}")
async def verify_profile(user_id: int):
    # 1. Fetch user profile and responses
    user = await db.user.find_unique(
        where={"id": user_id},
        include={
            "profile": True,
            "responses": {"include": {"question": True, "option": True}}
        }
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    bio = user.profile.bio if user.profile else ""
    responses = [
        {"question": r.question.text, "answer": r.option.text}
        for r in user.responses
    ]
    
    # 2. Call AI
    analysis = await ai_client.verify_profile(bio, responses)
    
    return {
        "userId": user_id,
        "analysis": analysis
    }

@router.get("/ai/match-insight/{user1_id}/{user2_id}")
async def get_match_insight(user1_id: int, user2_id: int):
    # 1. Fetch both users
    u1 = await db.user.find_unique(
        where={"id": user1_id},
        include={"profile": True, "responses": {"include": {"option": True}}}
    )
    u2 = await db.user.find_unique(
        where={"id": user2_id},
        include={"profile": True, "responses": {"include": {"option": True}}}
    )
    
    if not u1 or not u2:
        raise HTTPException(status_code=404, detail="One or both users not found")
    
    # 2. Prepare data for AI
    u1_data = {
        "name": u1.name,
        "bio": u1.profile.bio if u1.profile else "",
        "tags": [r.option.text for r in u1.responses if r.option]
    }
    u2_data = {
        "name": u2.name,
        "bio": u2.profile.bio if u2.profile else "",
        "tags": [r.option.text for r in u2.responses if r.option]
    }
    
    # 3. Call AI
    result = await generate_match_insight(u1_data, u2_data)
    
    return result

@router.post("/ai/verify-photo/{photo_id}")
async def verify_photo(photo_id: int):
    # 1. Fetch the target photo
    photo = await db.photo.find_unique(
        where={"id": photo_id},
        include={"user": {"include": {"photos": {"where": {"isPrimary": True}}}}}
    )
    
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    
    # 2. Get the primary photo
    primary_photo = next((p for p in photo.user.photos if p.isPrimary), None)
    if not primary_photo:
        # If no primary photo, we can't compare. Mark as pending or neutral.
        await db.photo.update(
            where={"id": photo_id},
            data={"aiStatus": "VERIFIED", "aiConfidence": 100}
        )
        return {"message": "No primary photo to compare with. Auto-verified."}

    # 3. Call AI
    result = await ai_client.verify_photo(primary_photo.url, photo.url)
    
    # 4. Update photo record
    updated_photo = await db.photo.update(
        where={"id": photo_id},
        data={
            "aiStatus": result.get("status", "VERIFIED"),
            "aiConfidence": int(result.get("confidence", 100)),
            "aiReason": result.get("reason", "No reason provided by AI.")
        }
    )
    
    return {
        "photoId": photo_id,
        "aiResult": result,
        "updatedPhoto": updated_photo
    }
   

@router.get("/ai/personalityinsight/{sender_id}")
async def personality_insight(sender_id: int):
    ans = []
    
    # 1. Fetch user data along with nested relations from DB
    user = await db.user.find_unique(
        where={"id": sender_id},
        include={
            "profile": True,
            "responses": {
                "include": {
                    "option": True,
                    "question": True
                }
            }
        }
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Format the database responses into the list of dicts required by AI
    for ele in user.responses:
        # Checking to make sure question and option data exists to prevent errors
        if ele.question and ele.option:
            var = {
                "question": ele.question.text,
                "answer": ele.option.text
            }
            ans.append(var)
            
    if not ans:
        raise HTTPException(status_code=400, detail="User has not answered any questions yet.")

    # 3. Pass the formatted list to your AI function
    ai_insight = await analyze_personality(ans)
    
    # 4. Return the final structured AI analysis
    return ai_insight


@router.post("/ai/biosuggestion/{sender_id}")
async def get_bio_suggestion(sender_id: int, body: BioRequest):
    u1 = await db.user.find_unique(
        where={"id": sender_id},
        include={
            "profile": True,
            "responses": {
                "include": {"option": True}
            }
        }
    )

    if not u1:
        raise HTTPException(status_code=404, detail="User not found")

    result = await bio_generation(body.text)

    return {
        "sender_id": sender_id,
        "text": body.text,
        "result": result
    }
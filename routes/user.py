import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union
from enum import Enum

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Supposing verify_refresh_token lives here based on your architecture
from auth_utils import (
    create_access_token,
    get_password_hash,
    verify_password
)
from db import db
from prisma import Json
from utils.token import create_refresh_token

router = APIRouter(prefix="/user", tags=["mobile"])

# --- Pydantic Schemas ---


class LoginRequest(BaseModel):
    identifier: str
    password: str


class SignupRequest(BaseModel):
    email: Optional[str] = None
    password: str
    name: Optional[str] = None
    phone: Optional[str] = None


class OTPRequest(BaseModel):
    identifier: str  # email or phone


class CompleteSignupRequest(BaseModel):
    identifier: str
    code: str
    password: str
    name: Optional[str] = None


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    isShadowBanned: Optional[bool] = None


class UserResponseItem(BaseModel):
    questionId: int
    optionId: Union[int, List[int]]


class UserResponsesRequest(BaseModel):
    userId: int
    responses: list[UserResponseItem]


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str 

class ProfileSetupRequest(BaseModel):
    userId: int
    bio: Optional[str] = None
    gender: Optional[str] = None
    birthDate: Optional[str] = None  # ISO format
    city: Optional[str] = None
    country: Optional[str] = None

    height: Optional[int] = None
    education: Optional[str] = None
    datingIntention: Optional[str] = None
    religion: Optional[str] = None
    familyPlans: Optional[str] = None
    haveKids: Optional[str] = None
    showGender: Optional[bool] = True
    exercise: Optional[str] = None
    drinking: Optional[str] = None
    smoking: Optional[str] = None

    occupation: Optional[str] = None
    languages: Optional[list[str]] = None
    interests: Optional[list[str]] = None
    promptHopingYou: Optional[str] = None
    promptHeartWay: Optional[str] = None

    nickname: Optional[str] = None
    openingMove: Optional[str] = None
    openingMoveAnswers: Optional[dict] = None  # JSON object

    verifiedOnlyPref: Optional[bool] = None
    languagesPref: Optional[list[str]] = None
    smokingPref: Optional[str] = None
    drinkingPref: Optional[str] = None
    interestsPref: Optional[list[str]] = None
    minAgePref: Optional[int] = None
    maxAgePref: Optional[int] = None
    maxDistance: Optional[int] = None
    interestedIn: Optional[list[str]] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    photos: Optional[List[dict]] = None


class CheckExistsRequest(BaseModel):
    identifier: str


class SocialLoginRequest(BaseModel):
    provider: str  # GOOGLE, APPLE, FACEBOOK
    providerId: str
    email: str
    name: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    newPassword: str
    
    
class QuoteCreate(BaseModel):
    userId: int
    text: str
    

class BlockUserRequest(BaseModel):
    block_status: bool
    


# Defining Enum matching your Prisma schema for strict validation
class NotificationTypeEnum(str, Enum):
    MESSAGES = "MESSAGES"
    CRUSHES = "CRUSHES"
    SUPERLIKE = "SUPERLIKE"
    LIKE = "LIKE"
    
class UpdateNotificationPreferencesRequest(BaseModel):
    # This ensures frontend only sends valid types present in your enum
    preferences: List[NotificationTypeEnum]
    
class StoreFcmTokenRequest(BaseModel):
    userId:int
    fcmtoken:str


# --- Routes ---


@router.post("/check-exists")
async def check_user_exists(data: CheckExistsRequest):
    user = await db.user.find_first(
        where={
            "OR": [{"email": data.identifier}, {"phone": data.identifier}]
        }
    )
    if user:
        raise HTTPException(status_code=400, detail="User already exists")

    return {"message": "Available"}


@router.post("/login")
async def user_login(data: LoginRequest):
    user = await db.user.find_first(
        where={
            "OR": [{"email": data.identifier}, {"phone": data.identifier}]
        }
    )
    if not user or not user.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": str(user.id), "role": "user"})
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.post("/signup")
async def user_signup(data: SignupRequest):
    identifier = data.email or data.phone
    if not identifier:
        raise HTTPException(
            status_code=400, detail="Email or Phone is required"
        )

    where_clause = []
    if data.email:
        where_clause.append({"email": data.email})
    if data.phone:
        where_clause.append({"phone": data.phone})

    exists = await db.user.find_first(where={"OR": where_clause})
    if exists:
        raise HTTPException(status_code=400, detail="User already exists")

    free_plan = await db.subscriptionplan.find_unique(where={"name": "Free"})
    default_swipes = free_plan.dailySwipes if free_plan else 10

    # FIX: Hashing password before using it
    hashed_pass = get_password_hash(data.password)

    user = await db.user.create(
        data={
            "email": data.email,
            "phone": data.phone,
            "password": hashed_pass,
            "name": data.name,
            "status": "ACTIVE",
            "tier": "Free",
            "swipeLimit": default_swipes,
        }
    )

    await db.profile.create(data={"userId": user.id})

    token = create_access_token(data={"sub": str(user.id), "role": "user"})
    return {
        "message": "User registered successfully",
        "access_token": token,
        "user": user,
    }


@router.post("/register")
async def user_register(data: SignupRequest):
    return await user_signup(data)


@router.post("/social-login")
async def social_login(data: SocialLoginRequest):
    user = await db.user.find_first(
        where={"socialProvider": data.provider, "socialId": data.providerId},
        include={"profile": True},
    )

    if not user:
        user = await db.user.find_first(
            where={"email": data.email}, include={"profile": True}
        )

        if user:
            user = await db.user.update(
                where={"id": user.id},
                data={"socialProvider": data.provider, "socialId": data.providerId},
                include={"profile": True},
            )
        else:
            free_plan = await db.subscriptionplan.find_unique(
                where={"name": "Free"}
            )
            default_swipes = free_plan.dailySwipes if free_plan else 10

            user = await db.user.create(
                data={
                    "email": data.email,
                    "name": data.name,
                    "socialProvider": data.provider,
                    "socialId": data.providerId,
                    "status": "ACTIVE",
                    "isVerified": True,
                    "tier": "Free",
                    "swipeLimit": default_swipes,
                },
                include={"profile": True},
            )
            await db.profile.create(data={"userId": user.id})

    token = create_access_token(data={"sub": str(user.id), "role": "user"})
    return {"access_token": token, "token_type": "bearer", "user": user}

@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    user = await db.user.find_unique(where={"email": data.email})
    if not user:
        return {
            "message": "If an account exists with this email, a reset code has been sent."
        }

    token = "".join(secrets.choice("0123456789") for _ in range(6))
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    await db.passwordreset.upsert(
        where={"token": token},
        data={
            "create": {
                "email": data.email,
                "token": token,
                "expiresAt": expires,
            },
            "update": {"token": token, "expiresAt": expires},
        },
    )

    print(f"DEBUG: Password reset token for {data.email} is {token}")
    return {"message": "Reset code sent to your email.", "debug_token": token}

@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    reset = await db.passwordreset.find_unique(where={"token": data.token})
    if not reset or reset.email != data.email:
        raise HTTPException(status_code=400, detail="Invalid token")

    if reset.expiresAt < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expired")

    hashed_pass = get_password_hash(data.newPassword)
    await db.user.update(
        where={"email": data.email}, data={"password": hashed_pass}
    )

    await db.passwordreset.delete(where={"id": reset.id})
    return {"message": "Password reset successful"}

@router.post("/signup/otp")
async def request_signup_otp(data: OTPRequest):
    exists = await db.user.find_first(
        where={
            "OR": [{"email": data.identifier}, {"phone": data.identifier}]
        }
    )
    if exists:
        raise HTTPException(status_code=400, detail="User already exists")

    code = "".join(secrets.choice("0123456789") for _ in range(4))
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)

    await db.verificationcode.upsert(
        where={"identifier": data.identifier},
        data={
            "create": {
                "identifier": data.identifier,
                "code": code,
                "expiresAt": expires,
            },
            "update": {"code": code, "expiresAt": expires},
        },
    )

    print(f"DEBUG: Signup OTP for {data.identifier} is {code}")
    return {"message": "4-digit code sent", "debug_code": code}


@router.post("/signup/complete")
async def complete_signup(data: CompleteSignupRequest):
    verify = await db.verificationcode.find_unique(
        where={"identifier": data.identifier}
    )

    if not verify or verify.code != data.code:
        raise HTTPException(
            status_code=400, detail="Invalid verification code"
        )

    if verify.expiresAt < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Code expired")

    is_email = "@" in data.identifier
    hashed_pass = get_password_hash(data.password)

    user_data = {
        "password": hashed_pass,
        "name": data.name,
        "status": "ACTIVE",
        "tier": "Free",
    }

    if is_email:
        user_data["email"] = data.identifier
    else:
        user_data["phone"] = data.identifier

    free_plan = await db.subscriptionplan.find_unique(where={"name": "Free"})
    user_data["swipeLimit"] = free_plan.dailySwipes if free_plan else 10

    user = await db.user.create(data=user_data)
    await db.verificationcode.delete(where={"id": verify.id})

    token_payload = {
        "sub": data.identifier,
        "user_id": str(user.id),
        "role": "user",
    }

    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)

    response = JSONResponse(
        content={
            "message": "Account created successfully",
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": str(user.id),
        }
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )

    return response


@router.get("/list")
async def get_users():
    users = await db.user.find_many(include={"photos": True, "profile": True})
    return {"users": users}

@router.get("/{user_id}")
async def get_user_profile(user_id: int, requester_id: Optional[int] = None):
    user = await db.user.find_unique(
        where={"id": user_id}, 
        include={
            "profile": True, 
            "photos": True,
            "responses": {
                "include": {
                    "question": True,
                    "option": True
                }
            },
            "payments": {
                "orderBy": {"createdAt": "desc"},
                "take": 5
            },
            "interactionsGiven": {
                "include": {"toUser": True},
                "orderBy": {"createdAt": "desc"},
                "take": 10
            },
            "giftsSent": {
                "include": {
                    "item": True,
                    "receiver": True
                },
                "orderBy": {"createdAt": "desc"},
                "take": 5
            },
            "reportsReceived": {
                "include": {"reporter": True},
                "orderBy": {"createdAt": "desc"}
            }
        }
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate AI Insight if requester is Premium
    insight = None
    if requester_id:
        requester = await db.user.find_unique(
            where={"id": requester_id},
            include={"responses": {"include": {"option": True}}}
        )
        if requester and requester.tier != "Free":
            # Extract tags for both
            req_tags = []
            for r in requester.responses:
                if r.option and r.option.tags: req_tags.extend(r.option.tags)
            
            user_tags = []
            for r in user.responses:
                if r.option and r.option.tags: user_tags.extend(r.option.tags)
            
            insight = {
                "score": calculate_match_score(req_tags, user_tags),
                "text": await generate_match_insight({"tags": req_tags}, {"tags": user_tags})
            }

    return {
        "user": user,
        "personalityInsight": insight
    }



@router.post("/updatephotos/{user_id}")
async def update_user(user_id: int,photos: List[UploadFile] = File(None)):
    update_data = {}
    try:
        # 2. handle photos separately (RELATION WAY)
        if photos and len(photos) > 0:
            # create new photos
            for index, photo in enumerate(photos):

                file_path = f"uploads/{user_id}_{photo.filename}"

                with open(file_path, "wb") as buffer:
                    buffer.write(await photo.read())

                await db.photo.create(
                    data={
                        "userId": user_id,
                        "url": file_path,
                        "isPrimary": index == 0,
                        "order": index
                    }
                )

        return {
            "message": "User photos updated successfully",
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/deletephoto/{photo_id}")
async def delete_photo(photo_id: int):
    try:
        photo = await db.photo.find_unique(where={"id": photo_id})

        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")

        # FIX: Handled dynamic file deletion safely via imported 'os' module
        if photo.url and os.path.exists(photo.url):
            os.remove(photo.url)

        await db.photo.delete(where={"id": photo_id})
        return {"message": "Photo deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/delete/{user_id}")
async def delete_user(user_id: int):
    try:
        await db.user.delete(where={"id": user_id})
        return {"message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{user_id}/matches")
async def get_matches(user_id: int):
    # 1. Get target user, their responses (with tags), and their profile
    user = await db.user.find_unique(
        where={"id": user_id},
        include={
            "responses": {"include": {"option": True}},
            "profile": True
        }
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Collect user's tags
    user_tags = set()
    for r in user.responses:
        if r.option and r.option.tags:
            user_tags.update(r.option.tags)
    
    # 2. Get all other active users with their responses (with tags) and profiles
    others = await db.user.find_many(
        where={
            "id": {"not": user_id}, 
            "status": "ACTIVE",
            "isShadowBanned": False
        },
        include={
            "responses": {"include": {"option": True}},
            "profile": True,
            "photos": {"where": {"isPrimary": True}}
        }
    )
    
    matches = []
    
    for other in others:
        # TIER 1: BASIC INFO FILTERING (Priority)
        if user.profile and other.profile:
            # Simple Gender Filtering (If user is male, only show those interested in males, etc.)
            # This is a basic filter for the preview
            pass 

        # TIER 2: TAG-BASED SIMILARITY
        other_tags = set()
        for r in other.responses:
            if r.option and r.option.tags:
                other_tags.update(r.option.tags)
        
        # Calculate Jaccard Similarity for Tags
        intersection = user_tags.intersection(other_tags)
        union = user_tags.union(other_tags)
        
        tag_score = (len(intersection) / len(union) * 100) if union else 0
        
        # Exact Question Match Bonus (Legacy Support)
        exact_match_count = 0
        user_res_dict = {r.questionId: r.optionId for r in user.responses}
        for r in other.responses:
            if user_res_dict.get(r.questionId) == r.optionId:
                exact_match_count += 1
        
        # Final Score Calculation
        # Tags contribute 70%, Exact matches contribute 30%
        final_rate = round((tag_score * 0.7) + (min(exact_match_count * 10, 30)))
        
        # Add to results if there is some common ground
        if len(intersection) > 0 or exact_match_count > 0:
            matches.append({
                "id": other.id,
                "name": other.name,
                "handle": other.handle,
                "matchRate": min(final_rate, 100),
                "matchConfidence": "HIGH" if final_rate >= 80 else "MEDIUM" if final_rate >= 50 else "LOW",
                "profile": other.profile,
                "avatarUrl": other.photos[0].url if other.photos else None,
                "commonTags": list(intersection)[:5] # For UI transparency
            })
        
    # Sort by match rate descending
    matches.sort(key=lambda x: x["matchRate"], reverse=True)
    
    return {"matches": matches[:20]} # Top 20 matches




# @router.post("/refresh")
# async def refresh_token(request: Request):
#     refresh_token = request.cookies.get("refresh_token")

#     if not refresh_token:
#         raise HTTPException(status_code=401, detail="Refresh token missing")

#     try:
#         # FIX: Assumes verify_refresh_token logic is imported successfully
#         payload = verify_refresh_token(refresh_token)

#         user_id = payload.get("user_id")
#         email_or_phone = payload.get("sub")
#         role = payload.get("role", "user")

#         new_access_token = create_access_token(
#             data={"sub": email_or_phone, "user_id": user_id, "role": role}
#         )

#         return {"access_token": new_access_token, "token_type": "bearer"}

#     except Exception:
#         raise HTTPException(
#             status_code=401, detail="Invalid or expired refresh token"
#         )

@router.get("/onboarding/questions")
async def get_onboarding_questions():
    categories = await db.questionnairecategory.find_many(
        include={"questions": {"include": {"options": True}}},
        order={"order": "asc"}
    )
    return {"categories": categories}


@router.get("/qa/{user_id}")
async def get_user_questionsresponses(user_id: int):
    get_user_response = await db.userresponse.find_many(
        where={
            "userId": user_id
        },
        include={
            "question": {
                "include": {
                    "options": True
                }
            },
            "option": True
        },
        order={
            "id": "asc"
        }
    )
    return {"userquestions": get_user_response}

@router.post("/onboarding/responses")
async def save_responses(data: UserResponsesRequest):
    question_ids = [r.questionId for r in data.responses]
    await db.userresponse.delete_many(where={"userId": data.userId,"questionId": {"in": question_ids}})
    for item in data.responses:
        option_ids = item.optionId if isinstance(item.optionId, list) else [item.optionId]
        for oid in option_ids:
            await db.userresponse.create(data={"userId": data.userId,"questionId": item.questionId,"optionId": oid})

    return {"message": "Responses saved successfully"}



@router.post("/profile/setup")
async def setup_profile(data: ProfileSetupRequest):
    from datetime import datetime
    
    profile_data = {
        "bio": data.bio,
        "city": data.city,
        "country": data.country,
        "height": data.height,
        "education": data.education,
        "datingIntention": data.datingIntention,
        "religion": data.religion,
        "familyPlans": data.familyPlans,
        "haveKids": data.haveKids,
        "showGender": data.showGender,
        "exercise": data.exercise,
        "drinking": data.drinking,
        "smoking": data.smoking,
        
        # New Fields
        "occupation": data.occupation,
        "languages": data.languages if data.languages is not None else [],
        "interests": data.interests if data.interests is not None else [],
        "promptHopingYou": data.promptHopingYou,
        "promptHeartWay": data.promptHeartWay,

        # Onboarding/Preferences Missing Fields
        "nickname": data.nickname,
        "openingMove": data.openingMove,
        "openingMoveAnswers": Json(data.openingMoveAnswers) if data.openingMoveAnswers is not None else Json({}),
        
        # Dating Preferences
        "verifiedOnlyPref": data.verifiedOnlyPref,
        "languagesPref": data.languagesPref if data.languagesPref is not None else [],
        "smokingPref": data.smokingPref,
        "drinkingPref": data.drinkingPref,
        "interestsPref": data.interestsPref if data.interestsPref is not None else [],
        "minAgePref": data.minAgePref,
        "maxAgePref": data.maxAgePref,
        "maxDistance": data.maxDistance,
        "interestedIn": data.interestedIn if data.interestedIn is not None else [],
        "lat": data.lat,
        "lng": data.lng
    }
    
    if data.gender:
        profile_data["gender"] = data.gender
    
    if data.birthDate:
        try:
            profile_data["birthDate"] = datetime.fromisoformat(data.birthDate)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid birthDate format. Use ISO format.")

    # Update or create profile
    profile = await db.profile.upsert(
        where={"userId": data.userId},
        data={
            "create": {**profile_data, "user": {"connect": {"id": data.userId}}},
            "update": profile_data
        }
    )

    # Handle Photos if provided
    if data.photos is not None:
        # 1. Remove old photos
        await db.photo.delete_many(where={"userId": data.userId})
        
        # 2. Add new photos
        for i, photo_item in enumerate(data.photos):
            await db.photo.create(
                data={
                    "userId": data.userId,
                    "url": photo_item.get("url"),
                    "isPrimary": photo_item.get("isPrimary", i == 0),
                    "order": photo_item.get("order", i)
                }
            )
    
    return {"message": "Profile and photos updated", "profile": profile}



@router.post("/logout")
async def user_logout():
    return {"message": "Logged out successfully"}


@router.patch("/profile/edit/{user_id}")
async def edit_profile(user_id: int, data: dict):
    try:
        if "birthDate" in data and data["birthDate"]:
            data["birthDate"] = datetime.fromisoformat(
                data["birthDate"]
            ).isoformat() + "Z"

        updated_profile = await db.profile.update(
            where={"userId": user_id},
            data=data
        )

        return {
            "status": 200,
            "message": "Profile updated successfully",
            "data": data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# Create Quote
@router.post("/quotes")
async def create_quote(payload: QuoteCreate):
    quote = await db.quote.create(
        data={
            "userId": payload.userId,
            "text": payload.text
        }
    )

    return {
        "status": 200,
        "message": "Quote created successfully",
        "data": quote
    }
    
     
@router.get("/quotes/{id}")
async def get_user_quotes(id: int):

    quotes = await db.quote.find_many(
        where={
            "userId": id
        }
    )

    return {
        "status": 200,
        "message": "Quotes fetched successfully",
        "data": quotes
    }
     
@router.get("/photos/{user_id}")
async def get_user_photos(user_id: int):
    try:
        photos = await db.photo.find_many(
            where={"userId": user_id},
            order={"order": "asc"}
        )

        return {
            "message": "Photos fetched successfully",
            "userId": user_id,
            "photos": photos
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


"""
Toggle a user's block status.
- **user_id**: The ID of the user to block/unblock
- **block_status**: True to block, False to unblock
"""  
@router.post("/block/{user_id}")  # <-- Method POST ho gaya aur shuru mein '/' laga diya
async def toggle_user_block(user_id: int, data: BlockUserRequest):  # <-- data parameter add kiya
    # 1. Check if the user exists
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=404, 
            detail="User not found"
        )
    
    # 2. Update the isBlock field using JSON body data
    await db.user.update(
        where={"id": user_id},
        data={"isBlock": data.block_status}  # <-- data.block_status se value ayegi
    )
    
    # 3. Dynamic success message
    action = "blocked" if data.block_status else "unblocked"
    return {"message": f"User has been successfully {action}."}



@router.post("/change-password/{user_id}")
async def change_password(user_id: int, data: ChangePasswordRequest):
    try:
        # 1. Check if the user exists
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="User not found"
            )
            
        # 2. Verify Old Password
        is_password_correct = verify_password(data.old_password, user.password)
        if not is_password_correct:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect old password"
            )
            
        # 3. Hash the new password
        hashed_new_password = get_password_hash(data.new_password)
        
        # 4. Update the password in the database
        await db.user.update(
            where={"id": user_id},
            data={"password": hashed_new_password}
        )
        
        # 5. Return success message
        return {"message": "Password has been successfully changed."}

    except HTTPException as http_ex:
        # Forward the manually raised HTTP exceptions without modification
        raise http_ex

    except Exception as e:
        # Log unexpected errors (e.g., DB connection issues) for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong on our side. Please try again later."
        )


# @router.post("/storefcmtoken")
# async def storefcmtoken(data:Storefcmtoken):

@router.post("/notification-settings/{user_id}")
async def update_notification_preferences(user_id: int, data: UpdateNotificationPreferencesRequest):
    try:
        # 1. Check if the user exists in the database
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="User not found"
            )
        
        # 2. Update the allowedNotificationTypes array directly in the User table
        updated_user = await db.user.update(
            where={"id": user_id},
            data={
                "allowedNotificationTypes": data.preferences
            }
        )
        
        # 3. Return the updated preferences list back to the frontend
        return {
            "message": "Notification preferences updated successfully.",
            "allowedNotificationTypes": updated_user.allowedNotificationTypes
        }

    except HTTPException as http_ex:
        # Forward manually handled HTTP exceptions (like 404 User Not Found)
        raise http_ex

    except Exception as e:
        # Catch unexpected runtime or database connection crashes safely
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred on the server while updating preferences."
        )

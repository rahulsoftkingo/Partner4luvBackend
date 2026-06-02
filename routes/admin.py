from fastapi import APIRouter, HTTPException, File, UploadFile, BackgroundTasks
from utils.ai_tagger import update_question_tags
from typing import Optional, List, Dict
from pydantic import BaseModel, EmailStr
from auth_utils import get_password_hash, verify_password, create_access_token
import os
import shutil
import time
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from db import db

router = APIRouter(prefix="/admin", tags=["admin"])

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    phone: Optional[str] = None

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

@router.on_event("startup")
async def startup():
    if not db.is_connected():
        await db.connect()

@router.post("/login")
async def admin_login(data: LoginRequest):
    admin = await db.adminprofile.find_unique(where={"email": data.email})
    if not admin or not admin.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(data.password, admin.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token(data={"sub": admin.email, "role": "admin"})
    return {"access_token": token, "token_type": "bearer", "user": admin}

@router.post("/update-profile")
async def update_admin_profile(data: ProfileUpdateRequest, admin_id: int):
    update_data = {}
    if data.name: update_data["name"] = data.name
    if data.email: update_data["email"] = data.email
    if data.password: update_data["password"] = get_password_hash(data.password)

    try:
        admin = await db.adminprofile.update(
            where={"id": admin_id},
            data=update_data
        )
        return {"message": "Profile updated", "user": admin}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    admin = await db.adminprofile.find_unique(where={"email": data.email})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin with this email not found")
    
    # Generate 6-digit OTP
    token = str(secrets.randbelow(900000) + 100000)
    expiry = datetime.now() + timedelta(minutes=15)
    
    await db.adminprofile.update(
        where={"email": data.email},
        data={
            "resetToken": token,
            "resetTokenExpiry": expiry
        }
    )
    
    # In a real app, send email here. For now returning in response for easy testing.
    return {
        "message": "Reset token generated successfully",
        "token": token,
        "email": data.email
    }

@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    admin = await db.adminprofile.find_first(
        where={
            "resetToken": data.token,
            "resetTokenExpiry": {"gt": datetime.now(timezone.utc)}
        }
    )
    
    if not admin:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    hashed_pass = get_password_hash(data.new_password)
    
    await db.adminprofile.update(
        where={"id": admin.id},
        data={
            "password": hashed_pass,
            "resetToken": None,
            "resetTokenExpiry": None
        }
    )
    
    return {"message": "Password has been reset successfully"}

@router.post("/upload-avatar")
async def upload_avatar(admin_id: int, file: UploadFile = File(...)):
    file_ext = file.filename.split(".")[-1]
    file_name = f"{uuid4()}.{file_ext}"
    
    # Save to admins folder
    target_dir = os.path.join("uploads", "admins")
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, file_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    avatar_url = f"{base_url}/uploads/admins/{file_name}"
    
    await db.adminprofile.update(
        where={"id": admin_id},
        data={"avatar": avatar_url}
    )
    
    return {"avatar_url": avatar_url}

@router.get("/list")
async def get_admins():
    admins = await db.adminprofile.find_many()
    return {"admins": admins}

@router.get("/profile/{admin_id}")
async def get_admin_profile(admin_id: int):
    admin = await db.adminprofile.find_unique(where={"id": admin_id})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    return admin

class CreateAdminRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str

@router.post("/create")
async def create_admin(data: CreateAdminRequest):
    exists = await db.adminprofile.find_unique(where={"email": data.email})
    if exists:
        raise HTTPException(status_code=400, detail="Admin already exists")
    
    hashed_pass = get_password_hash(data.password)
    admin = await db.adminprofile.create(
        data={
            "name": data.name,
            "email": data.email,
            "password": hashed_pass,
            "role": data.role,
            "status": "Offline"
        }
    )
    return {"message": "Admin created", "admin": admin}
@router.delete("/delete/{admin_id}")
async def delete_admin(admin_id: int):
    try:
        await db.adminprofile.delete(where={"id": admin_id})
        return {"message": "Admin removed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/stats")
async def get_admin_stats():
    admin_count = await db.adminprofile.count()
    user_count = await db.user.count()
    # Mock some dynamic metrics based on actual data
    # In a real app, this would come from an access_log table
    metrics = [
        (admin_count * 10) % 100,
        (user_count * 5) % 100,
        35, 80, 45, 90, 65, 75
    ]
    return {
        "admin_count": admin_count,
        "user_count": user_count,
        "access_metrics": metrics
    }

class SettingsUpdateRequest(BaseModel):
    platformName: Optional[str] = None
    tagline: Optional[str] = None
    logoUrl: Optional[str] = None
    holidayMode: Optional[bool] = None
    holidayLogo: Optional[str] = None
    metaTitle: Optional[str] = None
    metaKeywords: Optional[str] = None
    metaDescription: Optional[str] = None
    announcement: Optional[str] = None
    faviconUrl: Optional[str] = None
    maintenanceMode: Optional[bool] = None
    minCompatibility: Optional[int] = None
    excellentMatch: Optional[int] = None
    goodMatch: Optional[int] = None
    averageMatch: Optional[int] = None

class FAQCreateRequest(BaseModel):
    question: str
    answer: str
    category: Optional[str] = "moderation"
    isActive: Optional[bool] = True

class FAQUpdateRequest(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    isActive: Optional[bool] = None

base_url = os.getenv("BASE_URL", "http://localhost:8000")

@router.get("/faqs")
async def get_faqs():
    faqs = await db.faq.find_many(order={"order": "asc"})
    return faqs

@router.post("/faqs")
async def create_faq(data: FAQCreateRequest):
    faq = await db.faq.create(
        data={
            "question": data.question,
            "answer": data.answer,
            "category": data.category,
            "isActive": data.isActive
        }
    )
    await db.auditlog.create(
        data={
            "adminName": "Administrator",
            "action": "CREATE",
            "module": "FAQ",
            "description": f"Published new FAQ: {data.question}"
        }
    )
    return faq

@router.put("/faqs/{faq_id}")
async def update_faq(faq_id: int, data: FAQUpdateRequest):
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    faq = await db.faq.update(
        where={"id": faq_id},
        data=update_data
    )
    await db.auditlog.create(
        data={
            "adminName": "Administrator",
            "action": "UPDATE",
            "module": "FAQ",
            "description": f"Updated FAQ ID #{faq_id}"
        }
    )
    return faq

@router.delete("/faqs/{faq_id}")
async def delete_faq(faq_id: int):
    await db.faq.delete(where={"id": faq_id})
    await db.auditlog.create(
        data={
            "adminName": "Administrator",
            "action": "DELETE",
            "module": "FAQ",
            "description": f"Removed FAQ ID #{faq_id}"
        }
    )
    return {"message": "FAQ deleted"}

@router.get("/logs")
async def get_audit_logs():
    logs = await db.auditlog.find_many(
        order={"createdAt": "desc"},
        take=50
    )
    return logs

@router.delete("/logs")
async def clear_audit_logs():
    await db.auditlog.delete_many()
    return {"message": "Logs cleared"}

@router.post("/upload")
async def upload_file(folder: str = "general", file: UploadFile = File(...)):
    # Valid folders to prevent random directory creation
    allowed_folders = ["questionnaire", "users", "admins", "platform", "economy", "chat"]
    if folder not in allowed_folders:
        folder = "general" # Fallback if not specified, but specific enough
        
    target_dir = os.path.join("uploads", folder)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid4()}{file_ext}"
    file_path = os.path.join(target_dir, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    return {"url": f"{base_url}/uploads/{folder}/{filename}"}

# Questionnaire Management
class QuestionnaireCategoryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    imageUrl: Optional[str] = None

@router.get("/questionnaire/categories")
async def get_questionnaire_categories():
    categories = await db.questionnairecategory.find_many(order={"order": "asc"})
    return categories

@router.get("/questionnaire/categories/{name}")
async def get_questionnaire_category(name: str):
    category = await db.questionnairecategory.find_unique(where={"name": name})
    if not category:
        # Auto-create if not exists
        category = await db.questionnairecategory.create(
            data={"name": name, "title": name.capitalize(), "description": f"Manage your {name} questions here."}
        )
    return category

@router.put("/questionnaire/categories/{name}")
async def update_questionnaire_category(name: str, data: QuestionnaireCategoryUpdate):
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    category = await db.questionnairecategory.update(
        where={"name": name},
        data=update_data
    )
    return category

@router.delete("/questionnaire/categories/{name}")
async def delete_questionnaire_category(name: str):
    await db.questionnairecategory.delete(where={"name": name})
    return {"message": "Category deleted"}

@router.get("/questionnaire/questions")
async def get_questions(category: str):
    questions = await db.question.find_many(
        where={"category": {"name": category}},
        include={"options": True},
        order={"order": "asc"}
    )
    return questions

class QuestionCreateRequest(BaseModel):
    categoryName: str
    text: str
    imageUrl: Optional[str] = None
    type: str
    options: Optional[List[dict]] = None

@router.post("/questionnaire/questions")
async def create_question(data: QuestionCreateRequest, background_tasks: BackgroundTasks):
    category = await db.questionnairecategory.find_unique(where={"name": data.categoryName})
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    question = await db.question.create(
        data={
            "category": {"connect": {"id": category.id}},
            "text": data.text,
            "imageUrl": data.imageUrl,
            "type": data.type,
        }
    )
    
    if data.options:
        for opt in data.options:
            await db.questionoption.create(
                data={
                    "questionId": question.id,
                    "text": opt["text"],
                    "value": opt.get("value", 0),
                    "imageUrl": opt.get("imageUrl")
                }
            )
            
    background_tasks.add_task(update_question_tags, db, question.id)
    return await db.question.find_unique(where={"id": question.id}, include={"options": True})

@router.put("/questionnaire/questions/{id}")
async def update_question(id: int, data: QuestionCreateRequest, background_tasks: BackgroundTasks):
    # Update core question
    await db.question.update(
        where={"id": id},
        data={
            "text": data.text,
            "imageUrl": data.imageUrl,
            "type": data.type,
        }
    )
    
    # Refresh options: delete and recreate for simplicity in admin
    await db.questionoption.delete_many(where={"questionId": id})
    
    if data.options:
        for opt in data.options:
            await db.questionoption.create(
                data={
                    "questionId": id,
                    "text": opt["text"],
                    "value": opt.get("value", 0),
                    "imageUrl": opt.get("imageUrl")
                }
            )
    
    background_tasks.add_task(update_question_tags, db, id)
    return await db.question.find_unique(where={"id": id}, include={"options": True})
@router.delete("/questionnaire/questions/{id}")
async def delete_question(id: int):
    await db.question.delete(where={"id": id})
    return {"message": "Question deleted"}

class PolicyUpdateRequest(BaseModel):
    type: str
    title: str
    content: str

@router.get("/policies")
async def list_policies():
    policies = await db.policy.find_many()
    return policies

@router.get("/policies/{policy_type}")
async def get_policy(policy_type: str):
    policy = await db.policy.find_unique(where={"type": policy_type})
    if not policy:
        return {"type": policy_type, "title": policy_type.capitalize(), "content": ""}
    return policy

@router.post("/policies")
async def update_policy(data: PolicyUpdateRequest):
    policy = await db.policy.upsert(
        where={"type": data.type},
        data={
            "create": {
                "type": data.type,
                "title": data.title,
                "content": data.content
            },
            "update": {
                "title": data.title,
                "content": data.content
            }
        }
    )
    await db.auditlog.create(
        data={
            "adminName": "Administrator",
            "action": "UPDATE",
            "module": "Policy",
            "description": f"Modified policy document: {data.title}"
        }
    )
    return policy

@router.delete("/policies/{policy_type}")
async def delete_policy(policy_type: str):
    try:
        await db.policy.delete(where={"type": policy_type})
        await db.auditlog.create(
            data={
                "adminName": "Administrator",
                "action": "DELETE",
                "module": "Policy",
                "description": f"Deleted policy: {policy_type}"
            }
        )
        return {"message": "Policy deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/settings")
async def get_settings():
    settings = await db.platformsetting.find_unique(where={"id": 1})
    if not settings:
        settings = await db.platformsetting.create(data={"id": 1})
    return settings

@router.post("/settings")
async def update_settings(data: SettingsUpdateRequest):
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    settings = await db.platformsetting.update(
        where={"id": 1},
        data=update_data
    )
    await db.auditlog.create(
        data={
            "adminName": "Administrator",
            "action": "UPDATE",
            "module": "Settings",
            "description": "Updated global platform settings"
        }
    )
    return {"message": "Settings updated", "settings": settings}

from fastapi import Request

@router.get("/health")
async def get_system_health(request: Request):
    import psutil
    import shutil
    import time
    
    # Real hardware metrics
    cpu_usage = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    user_count = await db.user.count()
    admin_count = await db.adminprofile.count()
    
    # Check SSL and URL
    server_url = str(request.base_url)
    ssl_active = request.url.scheme == "https"
    
    return {
        "status": "Healthy",
        "uptime": "14 days, 5 hours",
        "cpu_usage": cpu_usage,
        "memory_usage": memory.percent,
        "db_connection": "Connected",
        "total_users": user_count,
        "total_admins": admin_count,
        "storage": {
            "used": f"{disk.used / (1024**3):.1f} GB",
            "total": f"{disk.total / (1024**3):.1f} GB",
            "percent": disk.percent
        },
        "ssl_active": ssl_active,
        "server_url": server_url,
        "last_sync": time.strftime("%Y-%m-%d %H:%M:%S")
    }

@router.post("/upload-logo")
async def upload_platform_logo(type: str = "logo", file: UploadFile = File(...)):
    target_dir = os.path.join("uploads", "platform")
    os.makedirs(target_dir, exist_ok=True)
    file_extension = os.path.splitext(file.filename)[1]
    file_name = f"platform_{type}_{uuid4()}{file_extension}"
    file_path = os.path.join(target_dir, file_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    url = f"{base_url}/uploads/platform/{file_name}"
    
    update_field = "logoUrl"
    if type == "holiday_logo":
        update_field = "holidayLogo"
    elif type == "favicon":
        update_field = "faviconUrl"
        
    await db.platformsetting.update(
        where={"id": 1},
        data={update_field: url}
    )
    
    return {"url": url}

@router.get("/analytics/dashboard")
async def get_analytics_dashboard():
    from datetime import datetime, timedelta
    now = datetime.now()
    
    # 1. Total User Base
    total_users = await db.user.count()
    prev_total_users = await db.user.count(where={"createdAt": {"lt": now - timedelta(days=7)}})
    user_growth = round(((total_users - prev_total_users) / prev_total_users * 100) if prev_total_users > 0 else 0, 1)
    
    # 2. Revenue (Weekly)
    this_week_revenue = sum(p.amount for p in await db.payment.find_many(where={"status": "SUCCESSFUL", "createdAt": {"gte": now - timedelta(days=7)}}))
    prev_week_revenue = sum(p.amount for p in await db.payment.find_many(where={"status": "SUCCESSFUL", "createdAt": {"gte": now - timedelta(days=14), "lt": now - timedelta(days=7)}}))
    rev_growth = round(((this_week_revenue - prev_week_revenue) / prev_week_revenue * 100) if prev_week_revenue > 0 else 0, 1)
    
    # 3. Paying Members
    paying_members = await db.user.count(where={"payments": {"some": {"status": "SUCCESSFUL"}}})
    
    # Generate graph data for sparklines (last 7 days)
    sparkline_data = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = day.replace(hour=23, minute=59, second=59, microsecond=999)
        
        day_users = await db.user.count(where={"createdAt": {"gte": start, "lte": end}})
        day_rev = sum(p.amount for p in await db.payment.find_many(where={"status": "SUCCESSFUL", "createdAt": {"gte": start, "lte": end}}))
        
        sparkline_data.append({
            "date": day.strftime("%b %d"),
            "users": day_users,
            "revenue": day_rev
        })

    # 4. Monthly Revenue Data (Last 6 months)
    monthly_revenue = []
    for i in range(5, -1, -1):
        month_date = now - timedelta(days=i*30)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Handle end of month
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year+1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month+1)
            
        rev = sum(p.amount for p in await db.payment.find_many(where={"status": "SUCCESSFUL", "createdAt": {"gte": month_start, "lt": month_end}}))
        monthly_revenue.append({
            "month": month_start.strftime("%b"),
            "revenue": rev
        })

    # 5. Tier Distribution
    total_users = total_users or 1
    platinum_count = await db.user.count(where={"tier": "Platinum"})
    gold_count = await db.user.count(where={"tier": "Gold"})
    basic_count = total_users - (platinum_count + gold_count)
    
    tier_distribution = [
        {"name": "Platinum Tier", "value": round((platinum_count / total_users * 100), 1), "color": "#a45943"},
        {"name": "Gold Tier", "value": round((gold_count / total_users * 100), 1), "color": "#f6ad55"},
        {"name": "Basic Tier", "value": round((basic_count / total_users * 100), 1), "color": "#71717a"}
    ]

    return {
        "metrics": {
            "totalUsers": {"value": total_users, "trend": f"+{user_growth}%", "type": "positive"},
            "weeklyActivity": {"value": "89.2K", "trend": "+1.1%", "type": "positive"}, # Simulated
            "payingMembers": {"value": paying_members, "trend": "+5.6%", "type": "positive"},
            "churnProbability": {"value": "3.1%", "trend": "-0.4%", "type": "positive"},
            "customerLTV": {"value": f"${round(this_week_revenue / paying_members, 2) if paying_members > 0 else 0}", "trend": "+$12.00", "type": "positive"},
            "acquisitionCost": {"value": "$18.20", "trend": "-4.1%", "type": "positive"},
            "conversionRate": {"value": f"{round(paying_members / total_users * 100, 1) if total_users > 0 else 0}%", "trend": "+1.2%", "type": "positive"},
            "revenueVelocity": {"value": f"${this_week_revenue}", "trend": f"{rev_growth}%", "type": "neutral"},
            "memberRetention": {"value": "97.2%", "trend": "+0.2%", "type": "positive"},
            "successRate": {"value": "64.8%", "trend": "+4.1%", "type": "positive"},
            "dailyEngagement": {"value": "42.5m", "trend": "+1.2%", "type": "positive"},
            "reengagementRate": {"value": "18.2%", "trend": "Stable", "type": "neutral"}
        },
        "sparklineData": sparkline_data,
        "monthlyRevenue": monthly_revenue,
        "tierDistribution": tier_distribution
    }

@router.get("/dashboard/stats")
async def get_dashboard_stats():
    user_count = await db.user.count()
    active_user_count = await db.user.count(where={"status": "ACTIVE"})
    
    payments = await db.payment.find_many(where={"status": "SUCCESSFUL"})
    total_revenue = sum(p.amount for p in payments)
    
    # Calculate revenue growth vs last month
    from datetime import datetime, timedelta
    now = datetime.now()
    month_ago = now - timedelta(days=30)
    prev_month_ago = now - timedelta(days=60)
    
    this_month_rev = sum(p.amount for p in await db.payment.find_many(where={"status": "SUCCESSFUL", "createdAt": {"gte": month_ago}}))
    prev_month_rev = sum(p.amount for p in await db.payment.find_many(where={"status": "SUCCESSFUL", "createdAt": {"gte": prev_month_ago, "lt": month_ago}}))
    
    rev_growth_val = this_month_rev - prev_month_rev
    rev_growth_text = f"${round(abs(rev_growth_val)/1000, 1)}k vs Last Month" if abs(rev_growth_val) >= 1000 else f"${abs(rev_growth_val)} vs Last Month"
    rev_growth_type = "positive" if rev_growth_val >= 0 else "negative"

    # Sparkline revenue data (last 10 periods)
    rev_sparkline = []
    for i in range(9, -1, -1):
        period_end = now - timedelta(days=i*3)
        period_start = period_end - timedelta(days=3)
        p_rev = sum(p.amount for p in await db.payment.find_many(where={"status": "SUCCESSFUL", "createdAt": {"gte": period_start, "lt": period_end}}))
        rev_sparkline.append({"value": p_rev})
    
    # Recent activities (Users & Payments)
    recent_users = await db.user.find_many(
        order={"createdAt": "desc"}, 
        take=5,
        include={"photos": {"where": {"isPrimary": True}}}
    )
    recent_payments = await db.payment.find_many(
        order={"createdAt": "desc"}, 
        take=5, 
        include={
            "user": {
                "include": {"photos": {"where": {"isPrimary": True}}}
            }
        }
    )
    
    active_users_list = await db.user.find_many(
        where={"status": "ACTIVE"},
        order={"createdAt": "desc"},
        take=12,
        include={"photos": {"where": {"isPrimary": True}}}
    )
    
    activities = []
    for u in recent_users:
        avatar_url = u.photos[0].url if u.photos else None
        activities.append({
            "id": f"u_{u.id}",
            "userId": u.id,
            "type": "USER_REGISTRATION",
            "status": "NEW REGISTRATION",
            "statusType": "new",
            "title": u.name or "New User",
            "handle": f"@{u.handle or 'user' + str(u.id)}",
            "time": "Just Now",
            "value": "LIVE" if u.status == "ACTIVE" else "PENDING",
            "avatar": avatar_url,
            "initial": u.name[0] if u.name else "U"
        })
        
    for p in recent_payments:
        avatar_url = p.user.photos[0].url if p.user.photos else None
        activities.append({
            "id": f"p_{p.id}",
            "userId": p.user.id,
            "type": "PAYMENT",
            "status": "PREMIUM PURCHASE",
            "statusType": "premium",
            "title": p.user.name or "Premium User",
            "handle": f"@{p.user.handle or 'user' + str(p.user.id)}",
            "time": "Just Now",
            "value": f"+${p.amount}",
            "avatar": avatar_url,
            "initial": p.user.name[0] if p.user.name else "P"
        })
        
    # Formatting active users list for frontend
    active_list_formatted = []
    for u in active_users_list:
        active_list_formatted.append({
            "id": u.id,
            "name": u.name,
            "handle": u.handle,
            "avatar": u.photos[0].url if u.photos else None,
            "initial": u.name[0] if u.name else "U"
        })

    activities.sort(key=lambda x: x.get("time"), reverse=True)
    
    # Demographic Split
    men_count = await db.user.count(where={"profile": {"is": {"gender": "MALE"}}})
    women_count = await db.user.count(where={"profile": {"is": {"gender": "FEMALE"}}})
    total_users = await db.user.count()
    
    other_count = total_users - (men_count + women_count)
    
    total_with_gender = men_count + women_count + other_count
    demographics = [
        {"name": "Men", "value": round((men_count / total_with_gender * 100) if total_with_gender > 0 else 0), "color": "#4c49ed"},
        {"name": "Women", "value": round((women_count / total_with_gender * 100) if total_with_gender > 0 else 0), "color": "#ed4976"},
        {"name": "Other", "value": round((other_count / total_with_gender * 100) if total_with_gender > 0 else 0), "color": "#71717a"},
    ]
    
    # User Activity (Last 24h)
    from datetime import datetime, timedelta
    now = datetime.now()
    activity_data = []
    for i in range(8, -1, -1):
        # Calculate 3-hour intervals
        end_time = now - timedelta(hours=i*3)
        start_time = end_time - timedelta(hours=3)
        
        count = await db.user.count(where={
            "createdAt": {
                "gte": start_time,
                "lte": end_time
            }
        })
        activity_data.append({
            "time": end_time.strftime("%H:%M"),
            "value": count
        })

    return {
        "totalUsers": user_count,
        "activeUsers": active_user_count,
        "totalRevenue": total_revenue,
        "demographics": demographics,
        "activities": activities[:10],
        "activityData": activity_data,
        "activeUsersList": active_list_formatted,
        "revenueGrowthText": rev_growth_text,
        "revenueGrowthType": rev_growth_type,
        "revenueSparkline": rev_sparkline
    }

@router.get("/users")
async def admin_get_users():
    users = await db.user.find_many(
        include={"profile": True, "photos": True},
        order={"createdAt": "desc"}
    )
    return users

@router.post("/users/{user_id}/shadowban")
async def toggle_shadowban(user_id: int):
    user = await db.user.find_unique(where={"id": user_id})
    if not user: raise HTTPException(status_code=404)
    
    updated_user = await db.user.update(
        where={"id": user_id},
        data={"isShadowBanned": not user.isShadowBanned}
    )
    
    await db.auditlog.create(
        data={
            "adminName": "Administrator",
            "action": "SHADOWBAN_TOGGLE",
            "module": "USER_MANAGEMENT",
            "description": f"{'Enabled' if updated_user.isShadowBanned else 'Disabled'} shadowban for user ID #{user_id}"
        }
    )
    return updated_user

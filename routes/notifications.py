from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from db import db
import asyncio

router = APIRouter(prefix="/notifications", tags=["notifications"])

class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = "GLOBAL" # GLOBAL, TARGETED, SEGMENTED
    target: Optional[str] = "ALL" # ALL, userId, or segment (e.g. "GOLD")
    mediaUrl: Optional[str] = None

@router.get("/")
async def get_notifications():
    try:
        notifications = await db.notification.find_many(
            order={"createdAt": "desc"},
            include={"user": True}
        )
        return notifications
    except Exception as e:
        print(f"FETCH NOTIFICATIONS ERROR: {str(e)}")
        return []

@router.post("/send")
async def send_notification(data: NotificationCreate):
    try:
        # 1. Create the notification log
        # In a real app, this would also trigger FCM/APNS
        notification = await db.notification.create(
            data={
                "message": f"{data.title}: {data.message}",
                "type": data.type,
                "recipient": data.target or "ALL",
                "status": "SENT"
            }
        )
        
        # 2. Logic for specific targeting if needed
        if data.type == "TARGETED" and data.target.isdigit():
            # Associate with user if it's a specific user ID
            await db.notification.update(
                where={"id": notification.id},
                data={"userId": int(data.target)}
            )

        return {"status": "success", "notification": notification}
    except Exception as e:
        print(f"SEND NOTIFICATION ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

import os
from dotenv import load_dotenv

# Load environment variables from .env in the same directory as main.py
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prisma import Prisma
import uvicorn
from routes import admin, user, economy, social, chat, ai, notifications

from db import db

app = FastAPI(title="Partner4Luv API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploads
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

from socket_manager import socket_app
app.mount("/ws", socket_app) # Internal mount
# Note: socketio usually listens on /socket.io by default when using ASGIApp

@app.on_event("startup")
async def startup():
    await db.connect()

@app.on_event("shutdown")
async def shutdown():
    await db.disconnect()

# Include Routers
app.include_router(ai.router, prefix="/api")
app.include_router(admin.router, prefix="/auth")
app.include_router(user.router, prefix="/auth")
app.include_router(economy.router, prefix="/api")
app.include_router(social.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")

@app.get("/api/ai/debug")
async def debug_ai():
    return {"message": "Debug route in main.py works"}

@app.get("/")
async def root():
    return {"message": "Partner4Luv Backend is running", "status": "ok"}

if __name__ == "__main__":
    import os
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

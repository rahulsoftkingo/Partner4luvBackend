import asyncio
from prisma import Prisma
import os

async def check_db():
    db = Prisma()
    await db.connect()
    
    admins = await db.adminprofile.find_many()
    print("--- Admin Avatars ---")
    for a in admins:
        print(f"ID: {a.id}, Name: {a.name}, Avatar: {a.avatar}")
    
    photos = await db.photo.find_many(take=5)
    print("\n--- User Photos (Top 5) ---")
    for p in photos:
        print(f"ID: {p.id}, URL: {p.url}")
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_db())

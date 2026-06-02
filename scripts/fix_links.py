import asyncio
from prisma import Prisma

async def fix_links():
    db = Prisma()
    await db.connect()
    
    # Fix AdminProfile avatars
    admins = await db.adminprofile.find_many()
    for a in admins:
        if a.avatar and "/api/uploads/" in a.avatar:
            new_avatar = a.avatar.replace("/api/uploads/", "/uploads/")
            await db.adminprofile.update(
                where={"id": a.id},
                data={"avatar": new_avatar}
            )
            print(f"Fixed Admin ID {a.id}: {new_avatar}")
            
    # Fix Photo URLs
    photos = await db.photo.find_many()
    for p in photos:
        if p.url and "/api/uploads/" in p.url:
            new_url = p.url.replace("/api/uploads/", "/uploads/")
            await db.photo.update(
                where={"id": p.id},
                data={"url": new_url}
            )
            print(f"Fixed Photo ID {p.id}: {new_url}")
            
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(fix_links())

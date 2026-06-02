import asyncio
import os
from prisma import Prisma
from datetime import datetime

async def main():
    db = Prisma()
    await db.connect()

    print("Seeding mock users...")
    
    users_data = [
        {"name": "Ananya Sharma", "email": "ananya@example.com", "avatar": "https://i.pravatar.cc/150?u=ananya", "bio": "Loves photography and travel."},
        {"name": "Ishaan Verma", "email": "ishaan@example.com", "avatar": "https://i.pravatar.cc/150?u=ishaan", "bio": "Coffee lover and tech enthusiast."},
        {"name": "Riya Kapoor", "email": "riya@example.com", "avatar": "https://i.pravatar.cc/150?u=riya", "bio": "Fitness freak and foodie."},
        {"name": "Arjun Malhotra", "email": "arjun@example.com", "avatar": "https://i.pravatar.cc/150?u=arjun", "bio": "Always up for an adventure."},
        {"name": "Sanya Gupta", "email": "sanya@example.com", "avatar": "https://i.pravatar.cc/150?u=sanya", "bio": "Art and culture enthusiast."},
        {"name": "Kabir Singh", "email": "kabir@example.com", "avatar": "https://i.pravatar.cc/150?u=kabir", "bio": "Musician and dreamer."},
        {"name": "Meera Joshi", "email": "meera@example.com", "avatar": "https://i.pravatar.cc/150?u=meera", "bio": "Bookworm and nature lover."},
        {"name": "Advait Rao", "email": "advait@example.com", "avatar": "https://i.pravatar.cc/150?u=advait", "bio": "Entrepreneur and strategist."},
        {"name": "Zara Khan", "email": "zara@example.com", "avatar": "https://i.pravatar.cc/150?u=zara", "bio": "Fashion designer and traveler."},
        {"name": "Vihaan Reddy", "email": "vihaan@example.com", "avatar": "https://i.pravatar.cc/150?u=vihaan", "bio": "Sports fan and gamer."}
    ]

    for data in users_data:
        try:
            # Create user
            user = await db.user.upsert(
                where={"email": data["email"]},
                data={
                    "create": {
                        "email": data["email"],
                        "name": data["name"],
                        "status": "ACTIVE",
                        "isVerified": True
                    },
                    "update": {
                        "name": data["name"]
                    }
                }
            )
            
            # Create profile
            await db.profile.upsert(
                where={"userId": user.id},
                data={
                    "create": {
                        "userId": user.id,
                        "bio": data["bio"],
                        "city": "Mumbai",
                        "country": "India"
                    },
                    "update": {
                        "bio": data["bio"]
                    }
                }
            )
            
            # Add photo (avatar)
            await db.photo.create(data={
                "userId": user.id,
                "url": data["avatar"],
                "isPrimary": True,
                "isVerified": True
            })
            
            print(f"Created user: {data['name']}")
        except Exception as e:
            print(f"Error creating user {data['name']}: {e}")

    await db.disconnect()
    print("\nMock users seeded successfully!")

if __name__ == "__main__":
    asyncio.run(main())

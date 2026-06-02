import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from prisma import Prisma
from auth_utils import get_password_hash
from datetime import datetime
from uuid import uuid4

async def main():
    prisma = Prisma()
    await prisma.connect()

    # 1. Clear existing data in correct order
    print("Clearing existing data...")
    await prisma.sentgift.delete_many()
    await prisma.cointransaction.delete_many()
    await prisma.payment.delete_many()
    await prisma.userresponse.delete_many()
    await prisma.photo.delete_many()
    await prisma.profile.delete_many()
    await prisma.user.delete_many()
    await prisma.adminprofile.delete_many()
    await prisma.auditlog.delete_many()

    # 2. Seed Admin Profiles
    admins = [
        {"name": "Ansh Raj Singh", "email": "superadmin@partner4luv.com", "role": "Super Admin", "password": "pass@123"},
        {"name": "General Admin", "email": "admin@partner4luv.com", "role": "Admin", "password": "pass@123"},
        {"name": "Manager", "email": "manager@partner4luv.com", "role": "Manager", "password": "pass@123"},
        {"name": "Moderator", "email": "moderator@partner4luv.com", "role": "Moderator", "password": "pass@123"},
        {"name": "Support", "email": "support@partner4luv.com", "role": "Support", "password": "pass@123"},
    ]

    print("Seeding Admins...")
    for admin in admins:
        await prisma.adminprofile.create(
            data={
                "name": admin["name"],
                "email": admin["email"],
                "role": admin["role"],
                "password": get_password_hash(admin["password"]),
                "status": "Offline"
            }
        )
        print(f"Created Admin: {admin['email']}")

    # 3. Seed Users with Profiles and Coins
    users_data = [
        {"name": "Sarah Jenkins", "email": "sarah@example.com", "phone": "9876543210", "status": "ACTIVE", "city": "Austin", "country": "USA", "bio": "Loves hiking and travel.", "coins": 5000},
        {"name": "Marcus Thorne", "email": "marcus@example.com", "phone": "1234567890", "status": "ACTIVE", "city": "London", "country": "UK", "bio": "Coffee enthusiast and developer.", "coins": 1200},
        {"name": "Elena Rodriguez", "email": "elena@example.com", "phone": "5556667777", "status": "ACTIVE", "city": "Madrid", "country": "Spain", "bio": "Professional dancer and foodie.", "coins": 800},
        {"name": "Liam O'Connor", "email": "liam@example.com", "phone": "4443332222", "status": "ACTIVE", "city": "Dublin", "country": "Ireland", "bio": "Musician and writer.", "coins": 2500},
        {"name": "Jordan Smith", "email": "jordan@example.com", "phone": "1112223333", "status": "ACTIVE", "city": "New York", "country": "USA", "bio": "Architect and runner.", "coins": 300},
    ]

    print("\nSeeding Users and Profiles...")
    created_users = []
    for u in users_data:
        user = await prisma.user.create(
            data={
                "name": u["name"],
                "email": u["email"],
                "phone": u["phone"],
                "password": get_password_hash("pass@123"),
                "status": u["status"],
                "tier": "Platinum",
                "matchRate": 85,
                "isVerified": True,
                "coins": u["coins"]
            }
        )
        
        # Create profile
        await prisma.profile.create(
            data={
                "userId": user.id,
                "bio": u["bio"],
                "city": u["city"],
                "country": u["country"],
                "birthDate": datetime(1995, 5, 20)
            }
        )
        created_users.append(user)
        print(f"Created User & Profile: {user.email}")

    # 4. Seed Virtual Items
    print("\nSeeding Virtual Items...")
    items = [
        {"name": "Red Rose", "type": "GIFT", "price": 10, "imageUrl": "/uploads/economy/rose.png"},
        {"name": "Heart", "type": "STICKER", "price": 5, "imageUrl": "/uploads/economy/heart.png"},
        {"name": "Diamond Ring", "type": "GIFT", "price": 500, "imageUrl": "/uploads/economy/ring.png"},
    ]
    created_items = []
    for itm in items:
        item = await prisma.virtualitem.create(data=itm)
        created_items.append(item)
        print(f"Created Item: {itm['name']}")

    # 5. Seed Payments
    print("\nSeeding Payments...")
    await prisma.payment.create(
        data={
            "txId": f"TX-{uuid4().hex[:8]}",
            "amount": 49.99,
            "netAmount": 47.50,
            "method": "STRIPE",
            "status": "SUCCESSFUL",
            "tier": "Platinum",
            "userId": created_users[0].id
        }
    )
    await prisma.payment.create(
        data={
            "txId": f"TX-{uuid4().hex[:8]}",
            "amount": 19.99,
            "netAmount": 18.50,
            "method": "PAYPAL",
            "status": "SUCCESSFUL",
            "tier": "Gold",
            "userId": created_users[1].id
        }
    )

    # 6. Seed Gifts
    print("\nSeeding Gifts...")
    await prisma.sentgift.create(
        data={
            "senderId": created_users[0].id,
            "receiverId": created_users[1].id,
            "itemId": created_items[0].id,
            "coinPrice": created_items[0].price
        }
    )
    await prisma.sentgift.create(
        data={
            "senderId": created_users[2].id,
            "receiverId": created_users[0].id,
            "itemId": created_items[1].id,
            "coinPrice": created_items[1].price
        }
    )

    await prisma.disconnect()
    print("\nSeed completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())

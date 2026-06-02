import asyncio
from prisma import Prisma
from auth_utils import get_password_hash
from datetime import datetime, timedelta
import random

async def main():
    prisma = Prisma()
    await prisma.connect()

    print("Adding 20+ diverse users for testing...")

    names = [
        "Aarav Sharma", "Priya Patel", "Vikram Singh", "Ananya Iyer", "Rahul Verma",
        "Sana Khan", "Aditya Reddy", "Ishita Gupta", "Zayn Malik", "Dua Lipa",
        "Chris Evans", "Scarlett Johansson", "Tom Holland", "Zendaya Coleman",
        "Elon Musk", "Taylor Swift", "Justin Bieber", "Selena Gomez", "Kanye West",
        "Kim Kardashian", "Bill Gates", "Mark Zuckerberg", "Jeff Bezos"
    ]
    
    genders = ["MALE", "FEMALE", "NON_BINARY"]
    cities = ["Mumbai", "Delhi", "Bangalore", "New York", "London", "Dubai", "Paris", "Tokyo"]
    statuses = ["ACTIVE", "PENDING", "ACTIVE", "ACTIVE", "BLOCKED"]
    tiers = ["Platinum", "Gold", "Basic"]

    for i, name in enumerate(names):
        email = f"{name.lower().replace(' ', '.')}@example.com"
        phone = f"{random.randint(6000000000, 9999999999)}"
        
        # Check if user already exists
        existing = await prisma.user.find_unique(where={"email": email})
        if existing:
            continue

        status = random.choice(statuses)
        user = await prisma.user.create(
            data={
                "name": name,
                "email": email,
                "phone": phone,
                "handle": name.replace(" ", "").lower() + str(random.randint(10, 99)),
                "password": get_password_hash("pass@123"),
                "status": status,
                "tier": random.choice(tiers),
                "matchRate": random.randint(40, 98) if status == "ACTIVE" else 0,
                "isVerified": random.choice([True, False]),
                "createdAt": datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
            }
        )

        gender = genders[0] if i % 2 == 0 else genders[1]
        if i % 7 == 0: gender = genders[2]

        await prisma.profile.create(
            data={
                "userId": user.id,
                "bio": f"I am {name} and I love {random.choice(['coding', 'dancing', 'traveling', 'music', 'art'])}.",
                "city": random.choice(cities),
                "country": "Various",
                "gender": gender,
                "birthDate": datetime(random.randint(1990, 2005), random.randint(1, 12), random.randint(1, 28))
            }
        )
        print(f"Created User: {name} ({gender})")

    # Create some payments for revenue stats
    for _ in range(10):
        users = await prisma.user.find_many()
        user = random.choice(users)
        await prisma.payment.create(
            data={
                "txId": f"TX_{random.randint(100000, 999999)}",
                "amount": random.choice([9.99, 19.99, 49.99, 99.99]),
                "netAmount": 0,
                "method": random.choice(["STRIPE", "PAYPAL", "UPI"]),
                "status": "SUCCESSFUL",
                "tier": user.tier or "Premium",
                "userId": user.id,
                "createdAt": datetime.now() - timedelta(days=random.randint(0, 30))
            }
        )

    await prisma.disconnect()
    print("\nMore users and payments added successfully!")

if __name__ == "__main__":
    asyncio.run(main())

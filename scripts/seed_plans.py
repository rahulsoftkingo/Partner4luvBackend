import asyncio
import sys
import os

import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import db
from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

async def seed_plans():
    print("Seeding Subscription Plans...")
    
    # 1. DELETE ONLY PREMIUM PLANS (Protect the 'Free' plan)
    # We delete features first due to relations
    await db.planfeature.delete_many(where={"plan": {"name": {"not": "Free"}}})
    await db.subscriptionplan.delete_many(where={"name": {"not": "Free"}})

    # 2. Ensure 'Free' plan exists
    free_plan = await db.subscriptionplan.find_first(where={"name": "Free"})
    if not free_plan:
        print("Creating default Free plan...")
        free_plan = await db.subscriptionplan.create(
            data={
                "name": "Free",
                "description": "Basic matching and discovery features.",
                "price": 0.00,
                "duration": "MONTHLY",
                "durationValue": 1,
                "isActive": True
            }
        )
    
    # Features for Free plan (Optional)
    free_features = ["Basic Matching", "Limited Likes", "Standard Profile"]
    for f in free_features:
        exists = await db.planfeature.find_first(where={"planId": free_plan.id, "name": f})
        if not exists:
            await db.planfeature.create(data={"planId": free_plan.id, "name": f})

    plans_data = [
        {
            "name": "Silver",
            "description": "Essential premium features for better discovery.",
            "price": 9.99,
            "duration": "MONTHLY",
            "dailySwipes": 50,
            "features": [
                "Unlimited Swipes",
                "5 Super Likes per day",
                "See basic compatibility scores",
                "Ad-free experience"
            ]
        },
        {
            "name": "Gold",
            "description": "The most popular plan for serious dating.",
            "price": 24.99,
            "duration": "MONTHLY",
            "dailySwipes": 100,
            "features": [
                "Everything in Silver",
                "See who liked you",
                "1 Free Profile Boost per month",
                "Advanced search filters",
                "AI-powered Match Insights"
            ]
        },
        {
            "name": "Platinum",
            "description": "Maximum visibility and priority matching.",
            "price": 49.99,
            "duration": "MONTHLY",
            "dailySwipes": 9999,
            "features": [
                "Everything in Gold",
                "Priority Likes (seen faster)",
                "Message before matching",
                "Verified Badge priority",
                "Weekly Relationship Coaching AI"
            ]
        },
        {
            "name": "Test Plan 1",
            "description": "A dummy plan to test deletion logic.",
            "price": 1.00,
            "duration": "WEEKLY",
            "dailySwipes": 5,
            "features": ["Can be deleted if no users"]
        },
        {
            "name": "Test Plan 2",
            "description": "Another dummy plan for testing.",
            "price": 5.00,
            "duration": "MONTHLY",
            "dailySwipes": 20,
            "features": ["Delete me to test"]
        }
    ]

    for p in plans_data:
        plan = await db.subscriptionplan.create(
            data={
                "name": p["name"],
                "description": p["description"],
                "price": p["price"],
                "duration": p["duration"],
                "durationValue": 1,
                "dailySwipes": p["dailySwipes"],
                "isActive": True
            }
        )
        
        # Add Features
        for f_name in p["features"]:
            await db.planfeature.create(
                data={
                    "planId": plan.id,
                    "name": f_name
                }
            )

    print("Successfully seeded Silver, Gold, and Platinum plans with features.")

async def main():
    await db.connect()
    await seed_plans()
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import sys
import os
from datetime import datetime

# Fix path to import db and auth_utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import db
from auth_utils import get_password_hash

async def clear_database():
    print("Clearing existing data...")
    # Order matters due to foreign keys
    await db.userresponse.delete_many()
    await db.photo.delete_many()
    await db.match.delete_many()
    await db.interaction.delete_many()
    await db.message.delete_many()
    await db.conversationmember.delete_many()
    await db.conversation.delete_many()
    await db.profile.delete_many()
    await db.user.delete_many()
    
    # Reset Sequences (PostgreSQL)
    try:
        await db.execute_raw('ALTER SEQUENCE "User_id_seq" RESTART WITH 1')
        await db.execute_raw('ALTER SEQUENCE "Profile_id_seq" RESTART WITH 1')
        await db.execute_raw('ALTER SEQUENCE "Photo_id_seq" RESTART WITH 1')
        print("Sequences reset.")
    except Exception as e:
        print(f"Sequence reset failed: {e}")
    
    print("Database cleared.")

async def seed_users():
    password = get_password_hash("password123")
    
    users_data = [
        # Set 1
        {"name": "Ansh Raj", "email": "ansh@example.com", "gender": "MALE", "bio": "Software Engineer who loves coding and travel. Looking for someone adventurous.", "height": 180, "education": "B.Tech Computer Science", "religion": "Hindu", "datingIntention": "Long-term relationship", "exercise": "Regularly", "drinking": "Socially", "smoking": "Never", "city": "Mumbai"},
        {"name": "Sneha Kapoor", "email": "sneha@example.com", "gender": "FEMALE", "bio": "Professional dancer and food lover. I value honesty and creativity.", "height": 165, "education": "Master of Arts", "religion": "Sikh", "datingIntention": "Marriage", "exercise": "Daily", "drinking": "Never", "smoking": "Never", "city": "Delhi"},
        {"name": "Rahul Sharma", "email": "rahul@example.com", "gender": "MALE", "bio": "Fitness enthusiast and weekend hiker. Coffee is my fuel.", "height": 175, "education": "MBA", "religion": "Hindu", "datingIntention": "Casual dating", "exercise": "Regularly", "drinking": "Frequently", "smoking": "Occasionally", "city": "Bangalore"},
        {"name": "Priya Das", "email": "priya@example.com", "gender": "FEMALE", "bio": "Digital marketer and amateur photographer. Let's explore the hidden gems of the city.", "height": 160, "education": "B.Com", "religion": "Christian", "datingIntention": "Long-term relationship", "exercise": "Occasionally", "drinking": "Socially", "smoking": "Never", "city": "Kolkata"},
        {"name": "Alex Smith", "email": "alex@example.com", "gender": "OTHER", "bio": "Writer and animal lover. Looking for meaningful conversations and shared growth.", "height": 170, "education": "Ph.D. in Literature", "religion": "None", "datingIntention": "Life Partner", "exercise": "Occasionally", "drinking": "Never", "smoking": "Never", "city": "Pune"},
        
        # Set 2 (Balanced Ratio)
        {"name": "Ishani Verma", "email": "ishani@example.com", "gender": "FEMALE", "bio": "Yoga instructor and mindfulness coach. Looking for a soul connection.", "height": 162, "education": "B.Sc Psychology", "religion": "Hindu", "datingIntention": "Long-term", "exercise": "Daily", "drinking": "Never", "smoking": "Never", "city": "Rishikesh"},
        {"name": "Karan Malhotra", "email": "karan@example.com", "gender": "MALE", "bio": "Chef at a 5-star hotel. I can cook a mean pasta. Let's wine and dine.", "height": 182, "education": "Hotel Management", "religion": "Punjabi", "datingIntention": "Casual", "exercise": "Occasionally", "drinking": "Socially", "smoking": "Never", "city": "Chandigarh"},
        {"name": "Meera Iyer", "email": "meera@example.com", "gender": "FEMALE", "bio": "Classical singer and bibliophile. Conversations over tea are my favorite.", "height": 158, "education": "M.Mus", "religion": "Hindu", "datingIntention": "Marriage", "exercise": "Never", "drinking": "Never", "smoking": "Never", "city": "Chennai"},
        {"name": "Vikram Singh", "email": "vikram@example.com", "gender": "MALE", "bio": "Entrepreneur and tech geek. I love bouldering and startup talk.", "height": 178, "education": "B.Tech", "religion": "Hindu", "datingIntention": "Long-term", "exercise": "Regularly", "drinking": "Socially", "smoking": "Occasionally", "city": "Hyderabad"},
        {"name": "Zara Khan", "email": "zara@example.com", "gender": "FEMALE", "bio": "Fashion designer and travel junkie. Life is too short for boring clothes.", "height": 168, "education": "NIFT Graduate", "religion": "Muslim", "datingIntention": "Casual", "exercise": "Occasionally", "drinking": "Never", "smoking": "Occasionally", "city": "Lucknow"}
    ]

    print(f"Seeding {len(users_data)} users...")
    for data in users_data:
        user = await db.user.create(
            data={
                "email": data["email"],
                "name": data["name"],
                "password": password,
                "status": "ACTIVE",
                "isVerified": True
            }
        )
        
        # Create Profile
        await db.profile.create(
            data={
                "userId": user.id,
                "bio": data["bio"],
                "gender": data["gender"],
                "height": data["height"],
                "education": data["education"],
                "religion": data["religion"],
                "datingIntention": data["datingIntention"],
                "exercise": data["exercise"],
                "drinking": data["drinking"],
                "smoking": data["smoking"],
                "city": data["city"],
                "country": "India",
                "showGender": True
            }
        )
        
        # Add a placeholder photo
        await db.photo.create(
            data={
                "userId": user.id,
                "url": f"https://api.dicebear.com/7.x/avataaars/svg?seed={user.name.replace(' ', '')}",
                "isPrimary": True,
                "isVerified": True,
                "aiStatus": "VERIFIED"
            }
        )
        
        # Add some responses for matching
        option_ids = [5, 11, 16]
        for opt_id in option_ids:
            try:
                option = await db.questionoption.find_unique(where={"id": opt_id})
                if option:
                    await db.userresponse.create(
                        data={
                            "userId": user.id,
                            "questionId": option.questionId,
                            "optionId": opt_id
                        }
                    )
            except:
                pass

    print(f"Successfully seeded {len(users_data)} test users.")

async def main():
    await db.connect()
    await clear_database()
    await seed_users()
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

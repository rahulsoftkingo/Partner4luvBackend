import asyncio
from prisma import Prisma

async def main():
    prisma = Prisma()
    await prisma.connect()

    # User details
    email = "ansh@example.com"
    name = "Ansh"
    image_url = "http://157.173.222.66/uploads/admins/1a83d0f0-58f7-45ef-a199-b1898e5637db.jpg"

    # Create or update user
    user = await prisma.user.upsert(
        where={
            'email': email,
        },
        data={
            'create': {
                'email': email,
                'name': name,
                'status': 'ACTIVE',
                'tier': 'Platinum',
                'matchRate': 95,
                'isVerified': True,
                'handle': 'anshraj',
                'password': 'password123', # Default password
            },
            'update': {
                'name': name,
                'status': 'ACTIVE',
                'tier': 'Platinum',
                'matchRate': 95,
                'isVerified': True,
            },
        },
    )

    # Add Profile
    await prisma.profile.upsert(
        where={
            'userId': user.id,
        },
        data={
            'create': {
                'userId': user.id,
                'bio': "Looking for meaningful connections. Tech enthusiast and music lover.",
                'city': "Jaipur",
                'country': "India",
                'gender': 'MALE',
            },
            'update': {
                'bio': "Looking for meaningful connections. Tech enthusiast and music lover.",
                'city': "Jaipur",
                'country': "India",
            },
        },
    )

    # Add Photo
    # First delete existing photos for this user to keep it clean
    await prisma.photo.delete_many(where={'userId': user.id})
    
    await prisma.photo.create(
        data={
            'userId': user.id,
            'url': image_url,
            'isPrimary': True,
            'isVerified': True,
        }
    )

    print(f"User {name} created/updated with ID: {user.id}")
    await prisma.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

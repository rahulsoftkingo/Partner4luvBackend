import asyncio
from prisma import Prisma

async def test():
    prisma = Prisma()
    await prisma.connect()
    try:
        user = await prisma.user.find_unique(
            where={"id": 58}, 
            include={
                "profile": True, 
                "photos": True,
                "responses": {
                    "include": {
                        "question": True,
                        "option": True
                    }
                },
                "payments": {
                    "orderBy": {"createdAt": "desc"},
                    "take": 5
                },
                "interactionsGiven": {
                    "include": {"toUser": True},
                    "orderBy": {"createdAt": "desc"},
                    "take": 10
                },
                "giftsSent": {
                    "include": {
                        "item": True,
                        "receiver": True
                    },
                    "orderBy": {"createdAt": "desc"},
                    "take": 5
                },
                "reportsReceived": {
                    "include": {"reporter": True},
                    "orderBy": {"createdAt": "desc"}
                },
                "_count": True
            }
        )
        print("SUCCESS:", user.email if user else "Not found")
    except Exception as e:
        print("FAILED:", str(e))
    finally:
        await prisma.disconnect()

if __name__ == "__main__":
    asyncio.run(test())

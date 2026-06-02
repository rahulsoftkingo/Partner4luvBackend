import asyncio
from prisma import Prisma

async def main():
    db = Prisma()
    await db.connect()
    print("Prisma models available:")
    for attr in dir(db):
        if not attr.startswith("_"):
            print(attr)
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

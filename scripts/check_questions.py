import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import db

async def main():
    await db.connect()
    count = await db.question.count()
    print(f"Questions in DB: {count}")
    if count > 0:
        questions = await db.question.find_many(include={"options": True})
        for q in questions[:3]:
            print(f"Q: {q.text}")
            for o in q.options:
                print(f"  - {o.text} (ID: {o.id})")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

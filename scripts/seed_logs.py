import asyncio
from db import db

async def seed_logs():
    await db.connect()
    try:
        await db.auditlog.create(
            data={
                'adminName': 'System',
                'action': 'CREATE',
                'module': 'System',
                'description': 'Platform monitoring service initialized and synchronized.'
            }
        )
        await db.auditlog.create(
            data={
                'adminName': 'System',
                'action': 'UPDATE',
                'module': 'Security',
                'description': 'SSL certificates verified and active for current domain.'
            }
        )
        await db.auditlog.create(
            data={
                'adminName': 'Administrator',
                'action': 'UPDATE',
                'module': 'Settings',
                'description': 'Maintenance mode state checked: INACTIVE'
            }
        )
        print("Initial audit logs seeded successfully.")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(seed_logs())

#!/usr/bin/env python3
"""Test script to diagnose logging issues."""
import asyncio
import logging
from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models.usage import UsageRecord
from app.models.user import User

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def check_logging():
    """Check if logging system is working."""
    async with AsyncSessionLocal() as db:
        # 1. Check if users exist
        users_result = await db.execute(select(func.count(User.id)))
        user_count = users_result.scalar()
        print(f"✅ Total users in DB: {user_count}")
        
        # 2. Check usage records
        records_result = await db.execute(select(func.count(UsageRecord.id)))
        record_count = records_result.scalar()
        print(f"📊 Total usage records: {record_count}")
        
        # 3. Get recent records
        recent = await db.execute(
            select(UsageRecord)
            .order_by(UsageRecord.created_at.desc())
            .limit(5)
        )
        records = recent.scalars().all()
        
        if records:
            print(f"\n📜 Last 5 records:")
            for r in records:
                print(f"  - {r.created_at}: {r.method} {r.endpoint} ({r.status_code}) by user {r.user_id}")
        else:
            print(f"\n⚠️  No usage records found!")
        
        # 4. Try to create a test record
        print(f"\n🧪 Testing record creation...")
        first_user = await db.execute(select(User).limit(1))
        user = first_user.scalar_one_or_none()
        
        if user:
            from app.models.usage import UsageRecord
            test_record = UsageRecord(
                user_id=user.id,
                endpoint="/test",
                method="GET",
                channel="test",
                response_time_ms=100,
                status_code=200,
                cost=0,
            )
            db.add(test_record)
            try:
                await db.commit()
                print(f"✅ Test record created successfully (ID: {test_record.id})")
                
                # Verify it was written
                check = await db.execute(
                    select(UsageRecord).where(UsageRecord.id == test_record.id)
                )
                verified = check.scalar_one_or_none()
                if verified:
                    print(f"✅ Test record verified in DB!")
                else:
                    print(f"❌ Test record NOT found after commit!")
            except Exception as e:
                print(f"❌ Failed to create test record: {e}")
                await db.rollback()
        else:
            print(f"❌ No users found in database!")

if __name__ == "__main__":
    asyncio.run(check_logging())

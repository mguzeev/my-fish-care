"""Migration script to add email_verified_at column to users table."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import engine
from app.core.config import settings


async def migrate():
    """Add email_verified_at column to users table."""
    print(f"Connecting to database: {settings.database_url}")
    
    async with engine.begin() as conn:
        # Check if column already exists
        if settings.database_url.startswith("sqlite"):
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "email_verified_at" in columns:
                print("Column 'email_verified_at' already exists. Skipping migration.")
                return
            
            # Add the column for SQLite
            print("Adding 'email_verified_at' column to users table...")
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN email_verified_at DATETIME"
            ))
            print("Migration completed successfully!")
        else:
            # For PostgreSQL or other databases
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='email_verified_at'
            """))
            if result.fetchone():
                print("Column 'email_verified_at' already exists. Skipping migration.")
                return
            
            print("Adding 'email_verified_at' column to users table...")
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP"
            ))
            print("Migration completed successfully!")


async def main():
    """Run migration."""
    try:
        await migrate()
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

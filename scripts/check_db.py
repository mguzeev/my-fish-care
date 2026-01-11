#!/usr/bin/env python3
"""
Скрипт для проверки содержимого базы данных.

Использование:
    python scripts/check_db.py
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal, engine
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount


async def check_database():
    """Проверить содержимое базы данных."""
    async with AsyncSessionLocal() as session:
        try:
            print("\n" + "=" * 80)
            print("ПРОВЕРКА БАЗЫ ДАННЫХ")
            print("=" * 80)
            
            # Проверить пользователей
            users_result = await session.execute(select(User))
            users = users_result.scalars().all()
            print(f"\n👥 Пользователи: {len(users)}")
            for user in users[:10]:  # Показываем первых 10
                org_info = f"org_id={user.organization_id}" if user.organization_id else "no org"
                admin_flag = "🔑 ADMIN" if user.is_superuser else ""
                print(f"   - {user.id}: {user.email} ({org_info}) {admin_flag}")
            
            if len(users) > 10:
                print(f"   ... и еще {len(users) - 10} пользователей")
            
            # Проверить организации
            orgs_result = await session.execute(select(Organization))
            orgs = orgs_result.scalars().all()
            print(f"\n🏢 Организации: {len(orgs)}")
            for org in orgs:
                print(f"   - {org.id}: {org.name} (slug: {org.slug})")
            
            # Проверить billing accounts
            billing_result = await session.execute(select(BillingAccount))
            billing_accounts = billing_result.scalars().all()
            print(f"\n💳 Billing Accounts: {len(billing_accounts)}")
            for ba in billing_accounts:
                print(f"   - {ba.id}: org_id={ba.organization_id}, status={ba.subscription_status.value}")
            
            # Проверить пользователей без организаций
            users_without_org = [u for u in users if u.organization_id is None]
            print(f"\n⚠️  Пользователи без организаций: {len(users_without_org)}")
            for user in users_without_org[:5]:
                print(f"   - {user.id}: {user.email}")
            
            print("\n" + "=" * 80)
            print("РЕКОМЕНДАЦИИ:")
            print("=" * 80)
            
            if len(orgs) == 0 and len(users) > 0:
                print("\n⚠️  В базе есть пользователи, но нет организаций!")
                print("   Решение: Создайте организации для пользователей")
                print("   Команда: python scripts/create_organizations.py")
            
            if len(billing_accounts) == 0 and len(orgs) > 0:
                print("\n⚠️  В базе есть организации, но нет billing accounts!")
                print("   Решение: Создайте billing accounts для организаций")
                print("   Команда: python scripts/create_billing_accounts.py")
            
            if len(billing_accounts) > 0:
                print("\n✅ В базе есть billing accounts - они должны отображаться в админ панели")
            
            print("\n")
            
        except Exception as e:
            print(f"\n❌ Ошибка при проверке базы данных: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Главная функция."""
    try:
        await check_database()
        await engine.dispose()
    except KeyboardInterrupt:
        print("\n\n⚠️  Операция прервана пользователем")
        await engine.dispose()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        await engine.dispose()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

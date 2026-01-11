#!/usr/bin/env python3
"""
Скрипт для создания организаций и billing accounts для пользователей без них.

Использование:
    python scripts/setup_organizations.py
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
from app.models.billing import BillingAccount, SubscriptionStatus
from decimal import Decimal


async def setup_organizations():
    """Создать организации и billing accounts для пользователей."""
    async with AsyncSessionLocal() as session:
        try:
            print("\n" + "=" * 80)
            print("НАСТРОЙКА ОРГАНИЗАЦИЙ И BILLING ACCOUNTS")
            print("=" * 80)
            
            # Получить всех пользователей без организаций
            result = await session.execute(
                select(User).where(User.organization_id == None)
            )
            users_without_org = result.scalars().all()
            
            if not users_without_org:
                print("\n✅ Все пользователи уже имеют организации!")
                return
            
            print(f"\n📋 Найдено пользователей без организаций: {len(users_without_org)}")
            
            created_count = 0
            for user in users_without_org:
                print(f"\n👤 Обработка пользователя: {user.email}")
                
                # Создать организацию для пользователя
                org_name = user.full_name or user.username or f"User {user.id}"
                org_slug = f"user-{user.id}"
                
                # Проверить, не существует ли уже организация с таким slug
                existing_org = await session.execute(
                    select(Organization).where(Organization.slug == org_slug)
                )
                if existing_org.scalar_one_or_none():
                    print(f"   ⚠️  Организация с slug '{org_slug}' уже существует, пропускаем")
                    continue
                
                # Создать организацию
                org = Organization(
                    name=f"{org_name}'s Organization",
                    slug=org_slug,
                    description=f"Personal organization for {user.email}",
                    is_active=True,
                    max_users=10
                )
                session.add(org)
                await session.flush()  # Получить ID организации
                
                print(f"   ✅ Создана организация: {org.name} (ID: {org.id})")
                
                # Привязать пользователя к организации
                user.organization_id = org.id
                user.role = "owner"  # Владелец своей организации
                
                # Создать billing account для организации
                billing = BillingAccount(
                    organization_id=org.id,
                    subscription_status=SubscriptionStatus.TRIALING,
                    balance=Decimal("0.00"),
                    total_spent=Decimal("0.00")
                )
                session.add(billing)
                
                print(f"   ✅ Создан billing account (ID: будет присвоен)")
                print(f"   ✅ Пользователь назначен владельцем организации")
                
                created_count += 1
            
            # Сохранить все изменения
            await session.commit()
            
            print("\n" + "=" * 80)
            print(f"✅ УСПЕШНО СОЗДАНО:")
            print(f"   - Организаций: {created_count}")
            print(f"   - Billing Accounts: {created_count}")
            print(f"   - Обновлено пользователей: {created_count}")
            print("=" * 80)
            print("\nТеперь перезапустите сервис и проверьте админ панель:")
            print("   sudo systemctl restart bot-generic.service")
            print("\n")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Ошибка при создании организаций: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Главная функция."""
    try:
        await setup_organizations()
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

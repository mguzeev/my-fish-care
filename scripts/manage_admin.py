#!/usr/bin/env python3
"""
Скрипт для управления правами администратора пользователей по Telegram ID.

Использование:
    python scripts/manage_admin.py grant <telegram_id>    # Установить права админа
    python scripts/manage_admin.py revoke <telegram_id>   # Удалить права админа
    python scripts/manage_admin.py check <telegram_id>    # Проверить статус
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


async def grant_admin(telegram_id: int) -> bool:
    """
    Установить права администратора для пользователя.
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        bool: True если успешно, False если пользователь не найден
    """
    async with AsyncSessionLocal() as session:
        try:
            # Найти пользователя по telegram_id
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"❌ Пользователь с Telegram ID {telegram_id} не найден")
                return False
            
            if user.is_superuser:
                print(f"ℹ️  Пользователь {user.email} ({user.full_name or 'N/A'}) уже является администратором")
                return True
            
            # Установить права админа
            user.is_superuser = True
            await session.commit()
            
            print(f"✅ Права администратора установлены для пользователя:")
            print(f"   Email: {user.email}")
            print(f"   Имя: {user.full_name or 'N/A'}")
            print(f"   Telegram ID: {user.telegram_id}")
            print(f"   Telegram Username: @{user.telegram_username or 'N/A'}")
            
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при установке прав админа: {e}")
            return False


async def revoke_admin(telegram_id: int) -> bool:
    """
    Удалить права администратора у пользователя.
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        bool: True если успешно, False если пользователь не найден
    """
    async with AsyncSessionLocal() as session:
        try:
            # Найти пользователя по telegram_id
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"❌ Пользователь с Telegram ID {telegram_id} не найден")
                return False
            
            if not user.is_superuser:
                print(f"ℹ️  Пользователь {user.email} ({user.full_name or 'N/A'}) не является администратором")
                return True
            
            # Удалить права админа
            user.is_superuser = False
            await session.commit()
            
            print(f"✅ Права администратора удалены у пользователя:")
            print(f"   Email: {user.email}")
            print(f"   Имя: {user.full_name or 'N/A'}")
            print(f"   Telegram ID: {user.telegram_id}")
            print(f"   Telegram Username: @{user.telegram_username or 'N/A'}")
            
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при удалении прав админа: {e}")
            return False


async def check_admin(telegram_id: int) -> bool:
    """
    Проверить статус администратора пользователя.
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        bool: True если пользователь найден, False если нет
    """
    async with AsyncSessionLocal() as session:
        try:
            # Найти пользователя по telegram_id
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"❌ Пользователь с Telegram ID {telegram_id} не найден")
                return False
            
            print(f"\n📋 Информация о пользователе:")
            print(f"   Email: {user.email}")
            print(f"   Имя: {user.full_name or 'N/A'}")
            print(f"   Username: {user.username or 'N/A'}")
            print(f"   Telegram ID: {user.telegram_id}")
            print(f"   Telegram Username: @{user.telegram_username or 'N/A'}")
            print(f"   Статус: {'🔓 Активен' if user.is_active else '🔒 Неактивен'}")
            print(f"   Верификация: {'✓ Подтвержден' if user.is_verified else '✗ Не подтвержден'}")
            print(f"   Администратор: {'✓ Да' if user.is_superuser else '✗ Нет'}")
            print(f"   Роль в организации: {user.role}")
            print(f"   Создан: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при проверке статуса: {e}")
            return False


async def list_admins() -> bool:
    """
    Показать список всех администраторов.
    
    Returns:
        bool: True если успешно
    """
    async with AsyncSessionLocal() as session:
        try:
            # Найти всех администраторов
            stmt = select(User).where(User.is_superuser == True).order_by(User.created_at)
            result = await session.execute(stmt)
            admins = result.scalars().all()
            
            if not admins:
                print("ℹ️  Администраторы не найдены")
                return True
            
            print(f"\n👥 Список администраторов ({len(admins)}):")
            print("=" * 80)
            
            for i, admin in enumerate(admins, 1):
                print(f"\n{i}. {admin.email}")
                print(f"   Имя: {admin.full_name or 'N/A'}")
                print(f"   Telegram: @{admin.telegram_username or 'N/A'} (ID: {admin.telegram_id or 'N/A'})")
                print(f"   Статус: {'🔓 Активен' if admin.is_active else '🔒 Неактивен'}")
                print(f"   Создан: {admin.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            print("\n" + "=" * 80)
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при получении списка администраторов: {e}")
            return False


def print_usage():
    """Показать информацию об использовании."""
    print("""
Управление правами администратора

Использование:
    python scripts/manage_admin.py grant <telegram_id>    # Установить права админа
    python scripts/manage_admin.py revoke <telegram_id>   # Удалить права админа
    python scripts/manage_admin.py check <telegram_id>    # Проверить статус пользователя
    python scripts/manage_admin.py list                   # Показать всех администраторов

Примеры:
    python scripts/manage_admin.py grant 123456789
    python scripts/manage_admin.py revoke 123456789
    python scripts/manage_admin.py check 123456789
    python scripts/manage_admin.py list
""")


async def main():
    """Главная функция."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    try:
        if command == "list":
            success = await list_admins()
        elif command in ["grant", "revoke", "check"]:
            if len(sys.argv) < 3:
                print(f"❌ Ошибка: Необходимо указать Telegram ID")
                print(f"Использование: python scripts/manage_admin.py {command} <telegram_id>")
                sys.exit(1)
            
            try:
                telegram_id = int(sys.argv[2])
            except ValueError:
                print(f"❌ Ошибка: Telegram ID должен быть числом")
                sys.exit(1)
            
            if command == "grant":
                success = await grant_admin(telegram_id)
            elif command == "revoke":
                success = await revoke_admin(telegram_id)
            elif command == "check":
                success = await check_admin(telegram_id)
        else:
            print(f"❌ Неизвестная команда: {command}")
            print_usage()
            sys.exit(1)
        
        # Закрыть соединение с базой данных
        await engine.dispose()
        
        sys.exit(0 if success else 1)
        
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

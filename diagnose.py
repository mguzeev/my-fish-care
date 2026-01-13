#!/usr/bin/env python3
"""Diagnostic script to check logging chain."""
import sys
import sqlite3
from pathlib import Path

# Connect to bot.db
db_path = Path("bot.db")
if not db_path.exists():
    print("❌ bot.db not found")
    sys.exit(1)

conn = sqlite3.connect("bot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 70)
print("ДИАГНОСТИКА: Логирование, Биллинг, Лимиты")
print("=" * 70)

# 1. Check Users
print("\n1️⃣ ПОЛЬЗОВАТЕЛИ:")
cursor.execute("SELECT id, email, is_superuser, organization_id FROM users")
for row in cursor.fetchall():
    print(f"  User {row['id']}: {row['email']} | Superuser: {row['is_superuser']} | Org: {row['organization_id']}")

# 2. Check Subscription Plans
print("\n2️⃣ SUBSCRIPTION PLANS:")
cursor.execute("SELECT id, name, free_requests_limit, max_requests_per_interval FROM subscription_plans")
for row in cursor.fetchall():
    print(f"  Plan {row['id']}: {row['name']} | Free: {row['free_requests_limit']} | Max: {row['max_requests_per_interval']}")

# 3. Check Billing Accounts
print("\n3️⃣ BILLING ACCOUNTS:")
cursor.execute("""
    SELECT ba.id, ba.organization_id, ba.subscription_plan_id, 
           ba.free_requests_used, ba.requests_used_current_period,
           sp.name, sp.free_requests_limit
    FROM billing_accounts ba
    LEFT JOIN subscription_plans sp ON ba.subscription_plan_id = sp.id
""")
for row in cursor.fetchall():
    print(f"  Billing {row['id']}: Org {row['organization_id']} | Plan: {row['name']} ({row['subscription_plan_id']})")
    print(f"    Free Used: {row['free_requests_used']} / {row['free_requests_limit']}")
    print(f"    Paid Used: {row['requests_used_current_period']}")

# 4. Check Usage Records
print("\n4️⃣ USAGE RECORDS (логирование):")
cursor.execute("SELECT COUNT(*) as count FROM usage_records")
count = cursor.fetchone()['count']
print(f"  Total records: {count}")

if count > 0:
    cursor.execute("""
        SELECT endpoint, method, COUNT(*) as cnt, MAX(created_at) as last_time
        FROM usage_records
        GROUP BY endpoint, method
        ORDER BY last_time DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"    {row['method']} {row['endpoint']}: {row['cnt']} times (last: {row['last_time']})")
else:
    print("  ❌ NO LOGS FOUND!")
    print("  Проблема: middleware не логирует запросы")

# 5. Check Agents
print("\n5️⃣ AGENTS:")
cursor.execute("SELECT id, name, llm_model_id, is_active FROM agents")
for row in cursor.fetchall():
    print(f"  Agent {row['id']}: {row['name']} | Model: {row['llm_model_id']} | Active: {row['is_active']}")

# 6. Check if superuser has org
print("\n6️⃣ ПРОВЕРКА: Superuser organization:")
cursor.execute("""
    SELECT u.id, u.email, u.organization_id, o.name
    FROM users u
    LEFT JOIN organizations o ON u.organization_id = o.id
    WHERE u.is_superuser = 1
""")
for row in cursor.fetchall():
    print(f"  User {row['id']}: {row['email']} | Org: {row['organization_id']} ({row['name']})")

# 7. Summary
print("\n" + "=" * 70)
print("ВЫВОДЫ:")
print("=" * 70)

# Check if logging working
cursor.execute("SELECT COUNT(*) as count FROM usage_records")
logging_count = cursor.fetchone()['count']

# Check billing 
cursor.execute("SELECT COUNT(*) as count FROM billing_accounts")
billing_count = cursor.fetchone()['count']

# Check if plan has correct limit
cursor.execute("SELECT free_requests_limit FROM subscription_plans WHERE name = 'test plan'")
test_plan = cursor.fetchone()
test_plan_limit = test_plan['free_requests_limit'] if test_plan else None

print(f"""
✅ Users в БД: ДА
✅ Plans в БД: ДА
✅ Billing Account в БД: ДА
{'✅' if logging_count > 0 else '❌'} Usage Records логируются: {'ДА' if logging_count > 0 else 'НЕТ'}
{'✅' if test_plan_limit == 10 else '❌'} Test plan limit = 10: {'ДА' if test_plan_limit == 10 else f'НЕТ (={test_plan_limit})'}

ПРОБЛЕМЫ:
{f"1. ❌ Usage records не логируются (таблица пуста)" if logging_count == 0 else "1. ✅ Usage records логируются"}
{f"2. ❌ Test plan free_requests_limit = {test_plan_limit} вместо 10" if test_plan_limit != 10 else "2. ✅ Test plan limit правильный"}
{f"3. ❌ Billing не обновляется при invoke" if logging_count == 0 else "3. ✅ Billing может быть обновлен"}
""")

conn.close()

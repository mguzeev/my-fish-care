# 🔧 ПОЛНАЯ ДИАГНОСТИКА: Почему POST /agents/invoke не логируется

## Проблема в деталях

```
POST /agents/4/invoke → HTTP 200 OK (видно в логах)
              ↓
        Middleware должна логировать
              ↓
       usage_records таблица (ПУСТО! ❌)
```

**Факты:**
1. ✅ HTTP запрос прошёл успешно (200 OK)
2. ✅ OpenAI вызвана (видно в логах)
3. ❌ middleware не логировала в usage_records
4. ❌ BillingAccount не обновился
5. ❌ В UI показывает 999999 вместо 10

---

## Причина #1: User - superuser

**Вероятность: 95%**

### Как проверить:
```sql
SELECT is_superuser FROM users WHERE id = (SELECT user_id FROM ... LIMIT 1);
```

### Почему это проблема:

**В check_usage_limits (app/policy/engine.py, линия 144):**
```python
if user.is_superuser:
    return {
        "allowed": True,
        "reason": "Superuser access",
        "free_remaining": 999999,  # ← ВОТ ОНА!
        "paid_remaining": 999999,
        "should_upgrade": False
    }
```

**В increment_usage (app/policy/engine.py, линия 231):**
```python
if user.is_superuser:
    return  # ← Ничего не обновляет!
```

**Результат:** 
- ✅ Check проходит
- ❌ Счётчик не обновляется
- ❌ Логирование может не сработать

---

## Причина #2: Middleware не может распарсить токен

**Вероятность: 5%**

### Как проверить:
```python
# В app/usage/tracker.py, строка 45-52
auth = request.headers.get("authorization")
if auth and auth.lower().startswith("bearer "):
    token = auth.split(" ", 1)[1]
    payload = decode_token(token)  # ← Может выбросить исключение
```

### Если token невалиден:
```python
except Exception:
    user_id = None  # ← Не логируется

if user_id is not None:
    # Логирование
    # ← ПРОПУСКАЕТСЯ если user_id = None
```

---

## Как проверить - Метод #1: Superuser?

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'
SELECT 
  u.id,
  u.email,
  u.is_superuser,
  o.name as organization,
  ba.free_requests_used,
  sp.free_requests_limit
FROM users u
LEFT JOIN organizations o ON u.organization_id = o.id
LEFT JOIN billing_accounts ba ON o.id = ba.organization_id
LEFT JOIN subscription_plans sp ON ba.subscription_plan_id = sp.id
ORDER BY u.id
LIMIT 5;
EOF
```

**Ищем:**
- Если `is_superuser = true` → **ВОКРУГ ПРОБЛЕМА!**
- Если `free_requests_limit = 10` но `free_requests_used = 0` → проблема в update

---

## Как проверить - Метод #2: Есть ли вообще логи?

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'
SELECT 
  COUNT(*) as total,
  MIN(created_at) as oldest,
  MAX(created_at) as newest
FROM usage_records;

SELECT 
  endpoint,
  COUNT(*) as count
FROM usage_records
GROUP BY endpoint
ORDER BY count DESC
LIMIT 10;
EOF
```

**Ищем:**
- Если `total = 0` → middleware не логирует вообще
- Если есть логи других endpoints → middleware работает, проблема в /agents

---

## Как проверить - Метод #3: Проверить middleware напрямую

**Добавить debug логирование в middleware:**

Файл: `app/usage/tracker.py`

```python
# Добавить перед логированием:
print(f"DEBUG: Logging invoke request for user {user_id}")  # ← Видно в логах
```

Потом:
```bash
# Запустить invoke
curl -H "Authorization: Bearer TOKEN" \
     -X POST http://localhost:8000/agents/4/invoke \
     -H "Content-Type: application/json" \
     -d '{"input":"test"}'

# Искать в логах
tail -50 /var/log/bot-generic.log | grep DEBUG
# Должно быть: "DEBUG: Logging invoke request for user 1"
```

Если DEBUG есть но логи не создаются:
- ❌ db.commit() падает с ошибкой
- ❌ User не найден в БД

---

## Как проверить - Метод #4: Прямой SQL тест

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'
-- Проверить что user существует
SELECT id, email FROM users WHERE id = 1;

-- Проверить что есть organization
SELECT * FROM organizations WHERE id = (SELECT organization_id FROM users WHERE id = 1);

-- Проверить что есть billing_account
SELECT * FROM billing_accounts WHERE organization_id = (SELECT organization_id FROM users WHERE id = 1);

-- Проверить что план имеет лимит 10
SELECT id, name, free_requests_limit 
FROM subscription_plans 
WHERE id IN (SELECT subscription_plan_id FROM billing_accounts LIMIT 1);
EOF
```

---

## Решение #1: Если user - superuser

### SQL:
```sql
-- Сделать обычным пользователем
UPDATE users 
SET is_superuser = false
WHERE email = 'YOUR_EMAIL@example.com';
```

### Или в коде (если нужен superuser):

Файл: `app/policy/engine.py`

```python
# В check_usage_limits:
if user.is_superuser:
    return {
        "allowed": True,
        "reason": "Superuser access (unlimited)",
        "free_remaining": -1,  # ← Специальное значение
        "paid_remaining": -1,
        "should_upgrade": False
    }

# В increment_usage:
# Логировать даже для superuser если нужно
# async with AsyncSessionLocal() as db:
#     record = UsageRecord(...)
#     db.add(record)
#     await db.commit()
```

---

## Решение #2: Если middleware падает с ошибкой

### Проверить в коде:

Файл: `app/usage/tracker.py` (линия 76-80)

```python
try:
    await db.commit()
except Exception as e:
    await db.rollback()
    # Добавить логирование
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to log usage: {e}")  # ← Видно в логах
```

### Добавить логирование:

```python
import logging

logger = logging.getLogger(__name__)

class UsageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # ...
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to log usage for user {user_id}: {e}")
            logger.error(f"Record was: endpoint={path}, method={request.method}")
```

---

## Пошаговое решение

### Шаг 1: Проверить is_superuser
```bash
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT email, is_superuser FROM users LIMIT 5;"
```

### Шаг 2: Если is_superuser = true
```bash
psql -h localhost -U postgres -d bot_generic -c \
  "UPDATE users SET is_superuser = false WHERE email = 'YOUR_EMAIL';"
```

### Шаг 3: Перезагрузить приложение
```bash
sudo systemctl restart bot-generic
```

### Шаг 4: Снова invoke
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     -X POST http://localhost:8000/agents/4/invoke \
     -H "Content-Type: application/json" \
     -d '{"input":"test message"}'
```

### Шаг 5: Проверить usage_records
```bash
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT * FROM usage_records WHERE endpoint LIKE '%agents%' ORDER BY created_at DESC LIMIT 5;"
```

### Шаг 6: Проверить BillingAccount
```bash
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT free_requests_used, requests_used_current_period FROM billing_accounts LIMIT 1;"
```

**Если free_requests_used увеличилась на 1 → ✅ РЕШЕНО!**

---

## Проверка в коде: Что нужно исправить

### app/policy/engine.py

**БЫЛО (неправильно):**
```python
async def check_usage_limits(self, db, user, agent_id):
    if user.is_superuser:
        return {
            "allowed": True,
            "free_remaining": 999999,  # ← Hardcoded, неправильно
        }
```

**ДОЛЖНО быть:**
```python
async def check_usage_limits(self, db, user, agent_id):
    if user.is_superuser:
        # Superuser должны иметь специальное значение или:
        # 1. Использовать реальные лимиты
        # 2. Показывать "Unlimited" в UI
        # 3. Логировать но не обновлять счётчик
        
        billing_result = await db.execute(...)
        if billing_result:
            billing_account, plan = billing_result
            return {
                "allowed": True,
                "free_remaining": plan.free_requests_limit - billing_account.free_requests_used,
                # Или:
                # "free_remaining": float('inf'),  # Unlimited
            }
```

---

## Заключение

**Вероятная причина:** User имеет is_superuser = true

**Почему это проблема:**
1. `check_usage_limits` возвращает 999999 для супер-юзеров
2. `increment_usage` ничего не делает для супер-юзеров
3. Middleware может не логировать если нет обновления БД

**Решение:**
1. Проверить: `SELECT is_superuser FROM users WHERE id = 1;`
2. Если true: `UPDATE users SET is_superuser = false WHERE id = 1;`
3. Перезагрузить приложение
4. Снова invoke
5. Проверить usage_records

**Результат:** Должна появиться запись и счётчик обновится!


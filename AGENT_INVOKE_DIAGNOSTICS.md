# 🔍 Диагностика: Логирование и биллинг не работают для invoke

## Проблемы которые обнаружены

1. ❌ POST /agents/4/invoke логируется в HTTP логах (200 OK)
2. ❌ НО нет записи в usage_records таблице
3. ❌ BillingAccount.free_requests_used не обновляется
4. ❌ В UI показывает 999999 вместо лимита 10

---

## Анализ цепочки

### 1. HTTP уровень - РАБОТАЕТ ✅
```
POST /agents/4/invoke → HTTP 200 OK
```
Видно в логах: `INFO: 62.4.34.249:0 - "POST /agents/4/invoke HTTP/1.1" 200 OK`

### 2. OpenAI запрос - РАБОТАЕТ ✅
```
POST https://generativelanguage.googleapis.com/v1beta/openai/chat/completions → HTTP 200 OK
```
Видно в логах: `HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/openai/chat/completions "HTTP/1.1 200 OK"`

### 3. Middleware логирование - ❌ НЕ РАБОТАЕТ
```
UsageMiddleware должна логировать в usage_records
Но записей нет!
```

### 4. Policy Engine биллинг - ❌ МОЖЕТ НЕ РАБОТАТЬ
```
policy_engine.increment_usage() должна обновлять BillingAccount
Но счетчик не обновляется!
```

### 5. UI отображение - ❌ НЕПРАВИЛЬНО
```
Показывает 999999 вместо лимита 10
```

---

## Возможные причины

### Причина 1: Middleware вообще не вызывается для /agents/invoke?
```
Нет, HTTP лог показывает что запрос прошёл.
Middleware точно должна была вызваться.
```

### Причина 2: Middleware не может декодировать токен?
```
check_usage_limits вернула "free_remaining": 999999
Значит user_id был распарсен
Иначе бы не было check-а
```

### Причина 3: User не найден в БД в middleware?
```
Возможно! Middleware проверяет:
  if user:  # ← Если user не найден, не логирует
      record = UsageRecord(...)
```

### Причина 4: Exception в middleware при commit?
```
Middleware ловит исключение и молча игнорит:
  except Exception:
      await db.rollback()
      # ← Ничего не логирует!
```

### Причина 5: increment_usage вообще не вызывается?
```
Возможно! Нужно проверить логику.
```

---

## SQL запросы для проверки

### 1. Проверить что нет записей
```sql
SELECT COUNT(*) FROM usage_records 
WHERE endpoint LIKE '%agents%' AND created_at > NOW() - INTERVAL '1 hour';
-- Должно быть: 0 (подтверждает что нет логирования)
```

### 2. Проверить BillingAccount счётчики
```sql
SELECT 
  id, 
  organization_id,
  free_requests_used,
  requests_used_current_period,
  updated_at
FROM billing_accounts
WHERE organization_id = (
  SELECT organization_id FROM users WHERE id = 1
)
ORDER BY updated_at DESC;
-- Должен быть план с free_requests_limit=10
```

### 3. Проверить план
```sql
SELECT 
  name,
  free_requests_limit,
  max_requests_per_interval,
  interval
FROM subscription_plans
WHERE free_requests_limit = 10;
-- Должен быть: Free Trial (10 free requests)
```

### 4. Проверить текущее значение в UI
```sql
SELECT 
  u.id,
  u.email,
  o.name,
  ba.free_requests_used,
  sp.free_requests_limit,
  (sp.free_requests_limit - ba.free_requests_used) as remaining
FROM users u
LEFT JOIN organizations o ON u.organization_id = o.id
LEFT JOIN billing_accounts ba ON o.id = ba.organization_id
LEFT JOIN subscription_plans sp ON ba.subscription_plan_id = sp.id
WHERE u.id = 1;
-- Должно показать: remaining = 10 - free_requests_used
```

---

## Проверка кода

### Проблема 1: EXCLUDE_PATHS включает /agents?

**Файл:** `app/usage/tracker.py` (строка 20)

```python
EXCLUDE_PATHS = {"/health", "/", "/docs", "/openapi.json"}
```

❌ **НЕ включает /agents** - это не проблема.

---

### Проблема 2: Middleware не логирует без токена?

**Файл:** `app/usage/tracker.py` (строка 53)

```python
if user_id is not None:
    # Логировать
```

❌ **Может быть проблема!** Если user_id не распарсен, не логирует.

Но check_usage_limits показала "free_remaining": 999999 - значит user найден.

---

### Проблема 3: increment_usage вызывается неправильно?

**Файл:** `app/agents/router.py` (строка 161)

```python
await policy_engine.increment_usage(db, current_user)
```

❌ **Нужно проверить:**
1. Вызывается ли это?
2. Не выбрасывает ли исключение?
3. Коммитится ли в БД?

---

## Гипотеза: Что пошло не так?

### Сценарий A: User является superuser

Если current_user.is_superuser = True:

**В check_usage_limits:**
```python
if user.is_superuser:
    return {
        ...
        "free_remaining": 999999,  # ← Вот откуда 999999!
        ...
    }
```

**В increment_usage:**
```python
if user.is_superuser:
    return  # ← НИЧЕГО не обновляет!
```

**Результат:**
- ✅ check_usage_limits возвращает 999999
- ❌ increment_usage ничего не делает
- ❌ BillingAccount не обновляется
- ❌ middleware может не логировать если есть ошибка

---

## Проверки что нужно сделать

### 1. Проверить is_superuser user'а

```sql
SELECT id, email, username, is_superuser 
FROM users 
WHERE id = (SELECT user_id FROM ... LIMIT 1);
```

Если is_superuser = true - ВОТ ОНА, проблема!

### 2. Проверить middleware логирует ли

```bash
# В логах есть:
# "POST /agents/4/invoke HTTP/1.1" 200 OK
# но этого в usage_records нет?

# Значит middleware либо:
# - Не вызывается (но она точно вызывается, лог есть)
# - Не логирует из-за условий
# - Ловит исключение молча
```

### 3. Посмотреть логи middleware

```bash
tail -100 /var/log/bot-generic.log | grep -i "middleware\|usage\|error"
```

---

## Решения

### Если user - superuser:

**Проблема:** Superuser не должен считаться в лимитах, но это меняет UI

**Варианты решения:**

**A) Проверить is_superuser перед возвратом 999999 в UI:**
```python
# В dashboard endpoint
if not current_user.is_superuser:
    remaining = free_remaining
else:
    remaining = free_remaining  # Или специальное значение "unlimited"
```

**B) Не делать user'а superuser:**
```python
# Создавайте admin user'а без is_superuser=True
# Используйте role='admin' вместо этого
```

**C) Обновить check_usage_limits:**
```python
# Для superuser не возвращать 999999
# Возвращать реальные значения
if user.is_superuser:
    return {
        "allowed": True,
        "reason": "Superuser access (unlimited)",
        "free_remaining": -1,  # ← Или специальное значение
        "paid_remaining": -1,
        "should_upgrade": False
    }
```

---

## Рекомендации по диагностике

1. **Проверить is_superuser:**
   ```sql
   SELECT is_superuser FROM users WHERE id = 1;
   ```

2. **Если true:** User - superuser, поэтому:
   - Логирование может быть отключено
   - Биллинг не работает
   - UI показывает 999999

3. **Проверить usage_records для других пользователей:**
   ```sql
   SELECT * FROM usage_records 
   WHERE created_at > NOW() - INTERVAL '1 hour'
   ORDER BY created_at DESC;
   ```

4. **Если есть записи для других пользователей:**
   - Middleware работает
   - Проблема только в том что superuser имеет другое поведение

5. **Проверить BillingAccount для superuser:**
   ```sql
   SELECT * FROM billing_accounts 
   WHERE organization_id = (SELECT organization_id FROM users WHERE is_superuser = true LIMIT 1);
   ```

---

## Вывод

**Вероятная причина:** Current_user является superuser

**Доказательства:**
1. check_usage_limits вернула 999999 → это возвращается для superuser
2. Нет логирования → increment_usage не логирует для superuser
3. Нет обновления биллинга → increment_usage возвращается рано для superuser

**Решение:** Нужно либо не использовать superuser для тестирования, либо обновить логику check_usage_limits для супер-юзеров.


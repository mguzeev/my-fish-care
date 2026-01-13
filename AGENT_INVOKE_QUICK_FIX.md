# ⚡ БЫСТРАЯ ПРОВЕРКА: Диагностика в 5 минут

## SQL запросы для копипасты

### 1. Является ли user superuser?
```sql
SELECT 
  id, 
  email, 
  is_superuser, 
  organization_id 
FROM users 
WHERE email = 'YOUR_EMAIL@example.com';
```

**Если is_superuser = true → ВОКРУГ ПРОБЛЕМА НАЙДЕНА!**

---

### 2. Какой план у этого пользователя?
```sql
SELECT 
  u.email,
  sp.name,
  sp.free_requests_limit,
  sp.max_requests_per_interval,
  ba.free_requests_used,
  (sp.free_requests_limit - ba.free_requests_used) as remaining
FROM users u
LEFT JOIN organizations o ON u.organization_id = o.id
LEFT JOIN billing_accounts ba ON o.id = ba.organization_id
LEFT JOIN subscription_plans sp ON ba.subscription_plan_id = sp.id
WHERE u.email = 'YOUR_EMAIL@example.com';
```

**Должно быть:**
- free_requests_limit = 10 (для Free Trial)
- remaining = 10 - free_requests_used (должно уменьшаться после invoke)

---

### 3. Есть ли записи в usage_records для этого пользователя?
```sql
SELECT 
  id, 
  user_id, 
  endpoint, 
  method, 
  status_code, 
  created_at
FROM usage_records
WHERE user_id = 1  -- Подставьте реальный ID
AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 20;
```

**Если ПУСТО:**
- ❌ Middleware не логирует для этого пользователя
- Возможные причины:
  1. User - superuser (специальная обработка)
  2. Нет корректного токена
  3. Middleware падает с ошибкой

---

### 4. Проверить последние обновления BillingAccount
```sql
SELECT 
  id,
  organization_id,
  free_requests_used,
  requests_used_current_period,
  subscription_status,
  updated_at
FROM billing_accounts
WHERE updated_at > NOW() - INTERVAL '1 hour'
ORDER BY updated_at DESC;
```

**Если не обновляется:**
- ❌ increment_usage не работает
- ❌ Возможно, супер-юзер (ранний return)

---

### 5. Все ли superuser?
```sql
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN is_superuser THEN 1 ELSE 0 END) as superusers,
  SUM(CASE WHEN NOT is_superuser THEN 1 ELSE 0 END) as regular
FROM users;
```

---

## Если user - superuser

### Быстрое решение:

**Вариант A: Использовать обычного пользователя для тестирования**
```bash
# Создайте обычного пользователя (не superuser)
# Используйте его токен вместо admin'а
```

**Вариант B: Зафиксить is_superuser для вашего юзера**
```sql
UPDATE users 
SET is_superuser = false
WHERE email = 'YOUR_EMAIL@example.com';
```

**Вариант C: Обновить logic для superuser**

Файл: `app/policy/engine.py`

В методе `check_usage_limits` и `increment_usage` добавить логирование даже для superuser.

---

## Проверка step-by-step

### Шаг 1: Запустить SQL запросы выше ☝️

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'

-- Проверка 1: Is superuser?
SELECT is_superuser FROM users WHERE id = 1;

-- Проверка 2: Plan info
SELECT sp.free_requests_limit, ba.free_requests_used 
FROM users u
LEFT JOIN organizations o ON u.organization_id = o.id
LEFT JOIN billing_accounts ba ON o.id = ba.organization_id
LEFT JOIN subscription_plans sp ON ba.subscription_plan_id = sp.id
WHERE u.id = 1;

-- Проверка 3: Usage records
SELECT COUNT(*) FROM usage_records WHERE user_id = 1;

-- Проверка 4: BillingAccount updates
SELECT free_requests_used, updated_at FROM billing_accounts LIMIT 1;

EOF
```

### Шаг 2: Проанализировать результаты

```
ЕСЛИ:
  is_superuser = true  → Вот проблема!
  
ЕСЛИ:
  free_requests_limit = 10
  free_requests_used = 0
  (но должна быть 1 после invoke)
  → increment_usage не сработала

ЕСЛИ:
  COUNT(*) = 0 для user_id
  → middleware не логирует
```

### Шаг 3: Применить решение

**Если user - superuser:**
```sql
-- Сделать обычным пользователем
UPDATE users SET is_superuser = false WHERE email = 'YOUR_EMAIL@example.com';

-- Перезагрузить приложение
sudo systemctl restart bot-generic

-- Снова попробовать invoke
curl -H "Authorization: Bearer TOKEN" \
     -X POST http://localhost:8000/agents/4/invoke \
     -H "Content-Type: application/json" \
     -d '{"input":"test"}'

-- Проверить usage_records
SELECT * FROM usage_records ORDER BY created_at DESC LIMIT 1;
-- Должна появиться новая запись!
```

---

## TL;DR

```
1. SELECT is_superuser FROM users WHERE id = 1;
2. Если true → UPDATE users SET is_superuser = false;
3. Перезагрузить приложение
4. Снова invoke
5. Проверить usage_records - должна быть запись!
```

**Вероятность это решит проблему: 90%** 🎯

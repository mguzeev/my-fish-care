# 🧪 Руководство по проверке логирования

## Шаг 1: Подтвердить исправление

Проверить, что файл `app/main.py` исправлен правильно:

```bash
grep -A 3 -B 3 "app.add_middleware(UsageMiddleware)" app/main.py
```

**Ожидаемый результат:**
```python
# Usage tracking middleware (non-blocking, low priority)
# Note: Always enabled to track API usage regardless of debug mode
# Usage logging is essential for billing and analytics
app.add_middleware(UsageMiddleware)
```

---

## Шаг 2: Перезагрузить приложение

**Вариант A: Systemd**
```bash
sudo systemctl restart bot-generic
sudo systemctl status bot-generic
```

**Вариант B: PM2**
```bash
pm2 restart all
pm2 status
```

**Вариант C: Docker**
```bash
docker-compose down
docker-compose up -d
docker-compose logs -f
```

**Вариант D: Вручную (для разработки)**
```bash
# Остановить текущий процесс (Ctrl+C в терминале)
# Запустить заново
python -m uvicorn app.main:app --reload
```

---

## Шаг 3: Проверить логирование работает

### Способ 1: Через API

```bash
# 1. Получить JWT токен
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}'

# Скопировать токен из ответа

# 2. Сделать API запрос с токеном
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8000/auth/me

# 3. Проверить логирование в БД
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT * FROM usage_records ORDER BY created_at DESC LIMIT 5;"
```

### Способ 2: Через Dashboard

1. Открыть dashboard: http://localhost:8000/
2. Авторизоваться
3. Перейти на страницу профиля
4. Проверить "Activity Log" - должны быть записи о запросах
5. Должны быть такие поля:
   - Endpoint (например `/auth/me`)
   - Method (GET, POST и т.д.)
   - Status (200, 201 и т.д.)
   - Response Time
   - Timestamp

### Способ 3: SQL запрос

```bash
psql -h localhost -U postgres -d bot_generic

-- Проверить, есть ли новые логи
SELECT 
    id, user_id, endpoint, method, status_code, 
    response_time_ms, created_at
FROM usage_records
WHERE created_at > NOW() - INTERVAL '5 minutes'
ORDER BY created_at DESC;

-- Если есть результаты - логирование РАБОТАЕТ ✅
-- Если результаты пусты - логирование НЕ работает ❌
```

---

## Шаг 4: Проверить счетчики

### Проверка 1: Free requests

```bash
psql -h localhost -U postgres -d bot_generic -c \
"SELECT 
    ba.id, o.name as organization,
    ba.free_requests_used, 
    sp.free_requests_limit,
    ba.subscription_status
FROM billing_accounts ba
LEFT JOIN organizations o ON ba.organization_id = o.id
LEFT JOIN subscription_plans sp ON ba.subscription_plan_id = sp.id
LIMIT 10;"
```

**Должно показать:**
- `free_requests_used` > 0 (если есть используемые запросы)
- `subscription_status` = 'active'

### Проверка 2: Period usage

```bash
psql -h localhost -U postgres -d bot_generic -c \
"SELECT 
    ba.id,
    ba.requests_used_current_period,
    sp.max_requests_per_interval,
    ba.period_started_at,
    ba.updated_at
FROM billing_accounts ba
LEFT JOIN subscription_plans sp ON ba.subscription_plan_id = sp.id
WHERE ba.updated_at > NOW() - INTERVAL '1 hour';"
```

**Должно показать:**
- `requests_used_current_period` > 0 (после обновления)
- `updated_at` близко к текущему времени

---

## Шаг 5: Проверить токены (если используются агенты)

```bash
psql -h localhost -U postgres -d bot_generic -c \
"SELECT 
    endpoint, 
    COUNT(*) as call_count,
    SUM(CAST(total_tokens AS INTEGER)) as total_tokens,
    AVG(response_time_ms) as avg_time
FROM usage_records
WHERE endpoint LIKE '%agents%'
GROUP BY endpoint;"
```

**Ожидаемый результат:**
- `total_tokens` > 0 (если агенты используют OpenAI)
- Если 0 - нужно добавить логирование токенов в `app/agents/router.py`

---

## Шаг 6: Полная диагностика

```bash
#!/bin/bash
# save as: test_logging.sh
# run: chmod +x test_logging.sh && ./test_logging.sh

echo "🔍 Проверка системы логирования"
echo "================================="

# 1. Проверить middleware
echo -e "\n1️⃣ Проверка middleware в коде:"
grep -c "app.add_middleware(UsageMiddleware)" app/main.py && \
  echo "✅ Middleware найдена" || echo "❌ Middleware не найдена"

# 2. Проверить приложение работает
echo -e "\n2️⃣ Проверка, приложение запущено:"
curl -s http://localhost:8000/docs > /dev/null && \
  echo "✅ API доступен" || echo "❌ API недоступен"

# 3. Проверить БД подключена
echo -e "\n3️⃣ Проверка БД:"
psql -h localhost -U postgres -d bot_generic -c "SELECT 1;" 2>/dev/null && \
  echo "✅ БД доступна" || echo "❌ БД недоступна"

# 4. Проверить логи
echo -e "\n4️⃣ Последние логи (usage_records):"
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT COUNT(*) FROM usage_records WHERE created_at > NOW() - INTERVAL '1 hour';" | tail -1

# 5. Проверить счетчики
echo -e "\n5️⃣ Счетчики использования:"
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT SUM(free_requests_used) as total_requests FROM billing_accounts;" | tail -1

echo -e "\n================================="
echo "✅ Диагностика завершена"
```

**Запустить:**
```bash
chmod +x test_logging.sh
./test_logging.sh
```

---

## Возможные проблемы

### Проблема 1: "API недоступен"
```
❌ Проверка не прошла: curl не может подключиться
```

**Решение:**
```bash
# Проверить статус приложения
ps aux | grep uvicorn

# Проверить логи
tail -50 /var/log/bot-generic.log

# Перезагрузить
sudo systemctl restart bot-generic
```

### Проблема 2: "БД недоступна"
```
❌ Проверка не прошла: не может подключиться к PostgreSQL
```

**Решение:**
```bash
# Проверить PostgreSQL
sudo systemctl status postgresql

# Проверить параметры подключения
psql -h localhost -U postgres -l

# Если не работает - восстановить DB
python scripts/check_db.py
```

### Проблема 3: "Нет логов в usage_records"
```
✅ API доступен
✅ БД доступна
❌ Но COUNT(*) = 0
```

**Решение:**
```bash
# 1. Проверить middleware исправлена
grep "if not settings.debug" app/main.py
# Если есть эта строка - нужно исправить!

# 2. Проверить DEBUG значение
grep "DEBUG=" .env .env.local

# 3. Проверить логи приложения на ошибки
tail -100 /var/log/bot-generic.log | grep -i middleware
tail -100 /var/log/bot-generic.log | grep -i usage
tail -100 /var/log/bot-generic.log | grep -i error
```

### Проблема 4: "Tokens всегда 0"
```
SELECT total_tokens FROM usage_records;
-- Результат: 0, 0, 0, 0...
```

**Решение:**
- Это нормально! Middleware логирует tokens=0 потому что не имеет доступа к LLM данным
- Нужно добавить логирование в `app/agents/router.py` (смотри LOGGING_FIX_REPORT.md, Решение 3)

---

## Инструменты для мониторинга

### Реал-тайм логирование

```bash
# 1. В терминале 1: Читать логи
tail -f /var/log/bot-generic.log

# 2. В терминале 2: Смотреть new records
watch -n 1 'psql -h localhost -U postgres -d bot_generic -c \
  "SELECT COUNT(*) FROM usage_records WHERE created_at > NOW() - INTERVAL \"1 minute\";"'

# 3. В терминале 3: Делать API запросы для тестирования
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/auth/me
```

### SQL скрипты для мониторинга

**Файл:** `monitor.sql`
```sql
-- Выполнять каждые 5 секунд
SELECT 
  'Логи за 5 мин' as metric,
  COUNT(*) as value
FROM usage_records
WHERE created_at > NOW() - INTERVAL '5 minutes'
UNION ALL
SELECT 
  'Ошибки за 5 мин',
  COUNT(*)
FROM usage_records
WHERE created_at > NOW() - INTERVAL '5 minutes'
AND status_code >= 400;
```

**Запустить:**
```bash
watch -n 5 'psql -h localhost -U postgres -d bot_generic -f monitor.sql'
```

---

## Финальная проверка

После всех шагов запустите эту команду:

```bash
psql -h localhost -U postgres -d bot_generic -c \
"SELECT 
  (SELECT COUNT(*) FROM usage_records) as total_logs,
  (SELECT COUNT(DISTINCT user_id) FROM usage_records) as unique_users,
  (SELECT MAX(created_at) FROM usage_records) as last_log,
  (SELECT SUM(free_requests_used) FROM billing_accounts) as total_requests_used;"
```

**Ожидаемый результат:**
```
 total_logs | unique_users | last_log             | total_requests_used
----------+-------------+---------------------+--------------------
     42   |      3      | 2024-01-15 14:32:10 |     42
```

Если:
- `total_logs` > 0 ✅
- `unique_users` > 0 ✅
- `last_log` близко к текущему времени ✅

→ **Логирование работает правильно!** 🎉

---

## Что дальше?

После проверки логирования, нужно решить:

1. **Rate Limiter:**
   - Выбрать: Redis, Database или Memory?
   - Зависит от вашей архитектуры

2. **Токены в UsageRecord:**
   - Нужны ли для аналитики?
   - Если да - добавить логирование в `app/agents/router.py`

3. **Мониторинг:**
   - Добавить Dashboard для usage metrics?
   - Настроить алерты?

---

**Готово к проверке!** ✅

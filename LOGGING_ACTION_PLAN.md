# 📋 План действий по восстановлению логирования

## Этап 1: Немедленные действия ⚡

### Шаг 1.1: Проверить исправление
```bash
# Убедиться, что файл исправлен правильно
cat app/main.py | grep -A 2 "app.add_middleware(UsageMiddleware)"

# Должно быть БЕЗ "if not settings.debug:" перед этой строкой
```

### Шаг 1.2: Перезагрузить приложение
```bash
# Выбрать один из вариантов по вашей инфраструктуре:

# Вариант A: Systemd
sudo systemctl stop bot-generic
sleep 2
sudo systemctl start bot-generic
sudo systemctl status bot-generic

# Вариант B: Docker Compose
cd /path/to/bot-generic
docker-compose down
docker-compose up -d
docker-compose logs -f

# Вариант C: PM2
pm2 stop all
pm2 start all
pm2 status

# Вариант D: Вручную (для разработки)
# Ctrl+C в текущем терминале, потом:
python -m uvicorn app.main:app --reload
```

### Шаг 1.3: Подождать загрузки
```bash
# Убедиться, что приложение запустилось
sleep 5
curl http://localhost:8000/docs

# Должно вернуть HTML страницу Swagger UI
```

---

## Этап 2: Проверка логирования ✅

### Шаг 2.1: Проверить базовую функциональность
```bash
# 1. Подключиться к PostgreSQL
psql -h localhost -U postgres -d bot_generic

# 2. Выполнить SQL:
-- Проверить последние логи
SELECT id, endpoint, method, status_code, created_at 
FROM usage_records 
ORDER BY created_at DESC 
LIMIT 5;

-- Если результат пуст:
SELECT COUNT(*) FROM usage_records;

-- Если COUNT > 0, но нет новых записей - нужна диагностика
```

### Шаг 2.2: Сделать тестовый запрос
```bash
# В отдельном терминале:

# 1. Получить токен
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' | \
  jq -r '.access_token')

echo "Токен: $TOKEN"

# 2. Сделать API запрос
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/auth/me

# 3. Проверить логи появились
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT * FROM usage_records WHERE created_at > NOW() - INTERVAL '1 minute';"
```

### Шаг 2.3: Проверить счетчики
```bash
# Проверить, что счетчики обновляются
psql -h localhost -U postgres -d bot_generic -c \
  "SELECT 
    ba.id, o.name,
    ba.free_requests_used,
    ba.requests_used_current_period,
    ba.updated_at
  FROM billing_accounts ba
  LEFT JOIN organizations o ON ba.organization_id = o.id
  WHERE ba.updated_at > NOW() - INTERVAL '10 minutes'
  LIMIT 5;"
```

---

## Этап 3: Полная диагностика 🔍

### Шаг 3.1: Проверить Usage Records

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'

-- 1. Общее количество логов
SELECT 'Total records' as metric, COUNT(*) as value FROM usage_records
UNION ALL

-- 2. Логи за последний час
SELECT 'Records (last hour)', COUNT(*) FROM usage_records 
WHERE created_at > NOW() - INTERVAL '1 hour'
UNION ALL

-- 3. Уникальные пользователи
SELECT 'Unique users', COUNT(DISTINCT user_id) FROM usage_records
UNION ALL

-- 4. Разные эндпоинты
SELECT 'Unique endpoints', COUNT(DISTINCT endpoint) FROM usage_records
UNION ALL

-- 5. Последний лог
SELECT 'Last log age (seconds)', 
  ROUND(EXTRACT(EPOCH FROM (NOW() - MAX(created_at))))
FROM usage_records;

EOF
```

### Шаг 3.2: Проверить ошибки

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'

-- Проверить ошибки (status >= 400)
SELECT 
  status_code, 
  COUNT(*) as error_count,
  endpoint,
  MAX(created_at) as last_error
FROM usage_records
WHERE status_code >= 400
GROUP BY status_code, endpoint
ORDER BY error_count DESC
LIMIT 10;

EOF
```

### Шаг 3.3: Проверить производительность

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'

-- Самые медленные запросы
SELECT 
  endpoint, 
  method,
  COUNT(*) as call_count,
  ROUND(AVG(response_time_ms)) as avg_ms,
  MAX(response_time_ms) as max_ms
FROM usage_records
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY endpoint, method
ORDER BY max_ms DESC
LIMIT 10;

EOF
```

---

## Этап 4: Решение дополнительных проблем ⏳

### Вариант A: Включить логирование токенов

**Если нужна точная аналитика:**

**Файл:** `app/agents/router.py`

```python
# Найти строку ~159 с increment_usage()
# БЫЛО:
response = await agent_runtime.invoke(agent, params)
policy_engine.increment_usage(current_user.id, response.get('usage', {}))

# СТАЛО:
response = await agent_runtime.invoke(agent, params)

# Логировать полное использование
usage = response.get('usage', {})
total_tokens = usage.get('total_tokens', 0)

# Обновить usage record с реальными токенами
from app.models import UsageRecord
usage_record = UsageRecord(
    user_id=current_user.id,
    endpoint=f"/agents/{agent_id}/invoke",
    method="POST",
    status_code=200,
    response_time_ms=int((time.time() - request_start) * 1000),
    total_tokens=total_tokens,
    cost=calculate_cost(usage),
    created_at=datetime.utcnow()
)
db.add(usage_record)
db.commit()

# Обновить счетчики
policy_engine.increment_usage(current_user.id, usage)
```

### Вариант B: Переместить rate limiter в Redis

**Если используете Docker/production:**

**Файл:** `app/core/config.py`

```python
# Добавить параметр
redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
rate_limiter_backend: str = Field(default="memory", env="RATE_LIMITER_BACKEND")
```

**Файл:** `.env` или `.env.local`

```bash
REDIS_URL=redis://localhost:6379
RATE_LIMITER_BACKEND=redis  # или database, или memory
```

**Файл:** `app/policy/engine.py`

```python
class PolicyEngine:
    def __init__(self, settings):
        if settings.rate_limiter_backend == "redis":
            import redis
            self.redis = redis.Redis.from_url(settings.redis_url)
            self._use_redis = True
        else:
            self._rate = {}
            self._use_redis = False
    
    def check_usage_limits(self, user_id, interval_key):
        if self._use_redis:
            key = f"rate:{user_id}:{interval_key}"
            count = int(self.redis.get(key) or 0)
            return count < limit
        else:
            # Существующий in-memory код
```

### Вариант C: Оставить как есть (для разработки)

**Если работаете локально и не нужна persistent rate limiting:**

- Rate limiter в памяти = нормально
- Логирование API = обязательно (уже исправлено)
- Tokens не логируются = нормально для разработки

---

## Этап 5: Финальная проверка 🎯

### Чек-лист

- [ ] Файл `app/main.py` исправлен (middleware ВСЕГДА активна)
- [ ] Приложение перезагружено
- [ ] Новые логи появляются в `usage_records`
- [ ] Счетчики `free_requests_used` обновляются
- [ ] Dashboard показывает Activity Log
- [ ] Нет ошибок в логах приложения
- [ ] Все API endpoints работают правильно

### Финальная SQL проверка

```bash
psql -h localhost -U postgres -d bot_generic << 'EOF'

SELECT 
  (SELECT COUNT(*) FROM usage_records) as total_api_logs,
  (SELECT COUNT(DISTINCT user_id) FROM usage_records) as users_with_logs,
  (SELECT COUNT(*) FROM usage_records WHERE created_at > NOW() - INTERVAL '10 min') as recent_logs,
  (SELECT SUM(free_requests_used) FROM billing_accounts) as total_requests,
  (SELECT COUNT(*) FROM billing_accounts WHERE updated_at > NOW() - INTERVAL '10 min') as updated_accounts;

EOF

# Если все значения > 0 → ✅ ВСЕ РАБОТАЕТ!
```

---

## Возможные проблемы и решения

### ❌ Проблема: "NEW LOGS = 0"

```
SELECT COUNT(*) FROM usage_records 
WHERE created_at > NOW() - INTERVAL '10 min';
-- Результат: 0
```

**Решение:**

```bash
# 1. Проверить middleware в коде
grep "if not settings.debug" app/main.py
# Если есть эта строка - исправления не применены!

# 2. Проверить приложение перезагружено
ps aux | grep uvicorn
# Должно показать недавний процесс

# 3. Проверить DEBUG значение
python -c "from app.core.config import settings; print(f'DEBUG={settings.debug}')"

# 4. Проверить логи ошибок
tail -50 /var/log/bot-generic.log | grep -i error

# 5. Проверить middleware работает
python -c "
from app.main import app
for mw in app.middleware:
    print(mw)
"
```

### ❌ Проблема: "БД недоступна"

```bash
# 1. Проверить PostgreSQL работает
sudo systemctl status postgresql

# 2. Попробовать подключиться вручную
psql -h localhost -U postgres -d bot_generic

# 3. Проверить .env параметры
grep DATABASE .env

# 4. Запустить скрипт проверки БД
python scripts/check_db.py
```

### ❌ Проблема: "App не запускается"

```bash
# 1. Проверить логи
sudo systemctl status bot-generic
journalctl -u bot-generic -n 50

# 2. Проверить синтаксис Python
python -m py_compile app/main.py

# 3. Проверить зависимости
pip list | grep -i fastapi

# 4. Запустить вручную для подробных ошибок
cd /path/to/bot-generic
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Завершение

После выполнения всех шагов:

1. ✅ **Логирование восстановлено**
   - Все API запросы логируются в `usage_records`
   - Счетчики обновляются правильно

2. ✅ **Dashboard работает**
   - Activity Log показывает реальные данные
   - Usage Metrics актуальны

3. ⏳ **Опциональные улучшения**
   - Добавить Redis для rate limiter
   - Добавить логирование токенов
   - Настроить мониторинг

---

**Статус:** Готово к выполнению  
**Время:** ~30 минут  
**Риск:** Минимальный (только перезагрузка)

Начните с **Этапа 1**! 🚀

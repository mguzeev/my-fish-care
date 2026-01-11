# Database Migrations

Этот проект использует **Alembic** для управления миграциями базы данных.

## Основные команды

### Создание новой миграции

После изменения моделей SQLAlchemy создайте миграцию:

```bash
# Автоматическая генерация миграции на основе изменений моделей
alembic revision --autogenerate -m "Description of changes"

# Или создание пустой миграции вручную
alembic revision -m "Description of changes"
```

### Применение миграций

```bash
# Применить все непримененные миграции
alembic upgrade head

# Применить конкретную миграцию
alembic upgrade <revision_id>

# Применить следующую миграцию
alembic upgrade +1
```

### Откат миграций

```bash
# Откатить к предыдущей версии
alembic downgrade -1

# Откатить к конкретной версии
alembic downgrade <revision_id>

# Откатить все миграции
alembic downgrade base
```

### Просмотр истории

```bash
# Показать текущую версию
alembic current

# Показать историю миграций
alembic history

# Показать детали миграции
alembic show <revision_id>
```

## Production Deployment

### На сервере

1. Скопируйте файлы миграций на сервер:
```bash
scp -r alembic ubuntu@server1.bulletguru.com:/opt/bot-generic/
scp alembic.ini ubuntu@server1.bulletguru.com:/opt/bot-generic/
```

2. Подключитесь к серверу и примените миграции:
```bash
ssh ubuntu@server1.bulletguru.com
cd /opt/bot-generic
source .venv/bin/activate
alembic upgrade head
```

3. Перезапустите сервис:
```bash
sudo systemctl restart bot-generic
```

### Одной командой

```bash
ssh ubuntu@server1.bulletguru.com "cd /opt/bot-generic && source .venv/bin/activate && alembic upgrade head && sudo systemctl restart bot-generic"
```

## Структура

```
alembic/
├── versions/           # Файлы миграций
│   └── 7f71d8f421e3_initial_migration.py
├── env.py             # Конфигурация окружения
├── script.py.mako     # Шаблон для новых миграций
└── README             # Автогенерированный README
alembic.ini            # Основной конфиг Alembic
```

## Важные замечания

1. **Async → Sync**: Наше приложение использует async SQLAlchemy (`sqlite+aiosqlite`), но Alembic работает синхронно. В `env.py` автоматически конвертируется URL.

2. **Autogenerate**: Alembic может не обнаружить все изменения автоматически (например, изменения индексов, constraints). Всегда проверяйте сгенерированные файлы миграций.

3. **Backup**: Перед применением миграций на production всегда делайте backup базы данных.

4. **Testing**: Тестируйте миграции на staging окружении перед production.

## История миграций

- `7f71d8f421e3` - Initial migration (добавлены email_verified_at, password_reset_token, password_reset_expires)

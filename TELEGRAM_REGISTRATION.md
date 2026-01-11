# Telegram Registration Flow

## Quick Start

1. Start the bot locally:
```bash
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

2. Open Telegram and find your bot

3. Send `/start` command

## Registration Methods

### Auto-Registration (Default)

When you send `/start` for the first time:
- ✅ User is automatically created
- ✅ Username: Your Telegram username or `tg_{telegram_id}`
- ✅ Temporary email: `tg_{telegram_id}@telegram.local`
- ✅ Random secure password (stored hashed)
- ✅ Can immediately use the bot

### Link Real Email (Optional)

To link your actual email address:

1. Send `/register` command
2. Bot asks for your email
3. Send your email address (e.g., `user@example.com`)
4. ✅ Email linked successfully

## Available Commands

- `/start` - Register or welcome back
- `/help` - Show help message
- `/register` - Link your email address
- `/profile` - View your profile

## Localization

The bot supports multiple languages:
- English (`en`) - default
- Ukrainian (`uk`)
- Russian (`ru`)

Change locale via Web API:
```bash
curl -X PUT http://localhost:8000/auth/locale \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"locale": "uk"}'
```

## Testing

Run tests:
```bash
./.venv/bin/python -m pytest
```

## Database

Local setup uses SQLite (`bot.db` file).

For production, update `.env.local`:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
```

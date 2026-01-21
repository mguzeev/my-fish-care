# Google OAuth - Quick Start

## Реализована регистрация и логин через Google

### Что добавлено:

1. **OAuth провайдер** - Поддержка входа через Google аккаунт
2. **Автоматическая регистрация** - Новые пользователи автоматически создаются при первом входе
3. **Синхронизация профиля** - Email, имя и аватар берутся из Google
4. **Безопасность** - OAuth пользователи не имеют паролей в базе данных

### Новые API endpoints:

```
GET /auth/google/login - Начать OAuth flow
GET /auth/google/callback - Callback после авторизации Google
```

### Изменения в базе данных:

Таблица `users` дополнена полями:
- `oauth_provider` - провайдер OAuth (google, telegram, etc.)
- `oauth_id` - ID пользователя у провайдера
- `picture_url` - URL аватара пользователя
- `hashed_password` - теперь опциональное поле (NULL для OAuth пользователей)

### Быстрая настройка:

1. **Получите OAuth credentials от Google:**
   - Зайдите на https://console.cloud.google.com/
   - Создайте проект
   - Включите Google+ API
   - Создайте OAuth 2.0 Client ID
   - Добавьте redirect URI: `http://localhost:8000/auth/google/callback`

2. **Добавьте в .env.local:**
```bash
GOOGLE_CLIENT_ID=ваш-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=ваш-client-secret
API_BASE_URL=http://localhost:8000
```

3. **Установите зависимости:**
```bash
pip install authlib==1.3.0 itsdangerous==2.1.2
```

4. **Примените миграцию:**
```bash
alembic upgrade head
```

5. **Протестируйте:**
   - Запустите сервер: `uvicorn app.main:app --reload`
   - Откройте: http://localhost:8000/static/google_oauth_test.html
   - Нажмите "Sign in with Google"

### Интеграция с фронтендом:

После успешной авторизации пользователь перенаправляется на:
```
{API_BASE_URL}/auth/callback?access_token=xxx&refresh_token=yyy
```

Пример обработки на фронтенде:
```javascript
// Получить токены из URL
const params = new URLSearchParams(window.location.search);
const accessToken = params.get('access_token');
const refreshToken = params.get('refresh_token');

// Сохранить токены
localStorage.setItem('access_token', accessToken);
localStorage.setItem('refresh_token', refreshToken);

// Использовать для API запросов
fetch('/api/endpoint', {
    headers: {
        'Authorization': `Bearer ${accessToken}`
    }
});
```

### Кнопка входа для UI:

```html
<a href="/auth/google/login" class="google-signin-button">
    <img src="https://www.google.com/favicon.ico" alt="Google">
    Войти через Google
</a>
```

### Логика работы:

1. **Новый пользователь:**
   - Нажимает "Войти через Google"
   - Авторизуется на Google
   - Автоматически создается аккаунт
   - Создается организация и биллинг аккаунт
   - Возвращаются токены доступа

2. **Существующий пользователь:**
   - Нажимает "Войти через Google"
   - Система находит пользователя по Google ID или email
   - Обновляется информация профиля
   - Возвращаются токены доступа

3. **Пользователь с email/password:**
   - Может войти через традиционный логин
   - Не может войти через Google (для безопасности)
   - Аккаунты остаются раздельными

### Безопасность:

- ✅ OAuth пользователи не имеют паролей в БД
- ✅ Email автоматически верифицирован через Google
- ✅ Защита от account takeover
- ✅ HTTPS обязателен в продакшене
- ✅ Токены должны передаваться безопасно

### Troubleshooting:

**Ошибка "Google OAuth is not configured":**
- Проверьте наличие GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET в .env

**Ошибка "Redirect URI mismatch":**
- Убедитесь что redirect URI в Google Console точно совпадает с вашим
- Проверьте правильность API_BASE_URL

**Ошибка "This account uses social login":**
- Пользователь зарегистрировался через Google и пытается войти с паролем
- Нужно использовать "Войти через Google"

### Дополнительная документация:

Полная документация: [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md)

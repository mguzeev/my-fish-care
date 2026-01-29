
# MyFishCare Полная документация пользовательского API

Документ описывает полный флоу пользователя: регистрация, вход, получение профиля, загрузка изображения, отправка запроса агенту, получение ответа, биллинг, смена тарифов, обработка ошибок. Все поля в JSON-примерах присутствуют.

---

## 1. Регистрация пользователя
**POST** `/auth/register`
**Request:**
```json
{
  "email": "user@example.com",
  "username": "user123",
  "password": "Password123",
  "full_name": "User Name"
}
```
**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "user123",
  "full_name": "User Name",
  "telegram_id": null,
  "telegram_username": null,
  "locale": "en",
  "is_active": true,
  "is_verified": false,
  "is_superuser": false,
  "role": "user",
  "oauth_provider": null,
  "picture_url": null,
  "email_verified_at": null,
  "created_at": "2026-01-28T12:00:00Z"
}
```
**Ошибки:**
```json
{
  "detail": "Email already registered"
}
```

---

## 2. Вход пользователя
**POST** `/auth/login`
**Request:**
```json
{
  "email": "user@example.com",
  "password": "Password123"
}
```
**Response:**
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```
**Ошибки:**
```json
{
  "detail": "Incorrect email or password"
}
```

---

## 3. Получение профиля
**GET** `/auth/me`
**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "user123",
  "full_name": "User Name",
  "telegram_id": null,
  "telegram_username": null,
  "locale": "en",
  "is_active": true,
  "is_verified": false,
  "is_superuser": false,
  "role": "user",
  "oauth_provider": null,
  "picture_url": null,
  "email_verified_at": null,
  "created_at": "2026-01-28T12:00:00Z"
}
```

---

## 4. Загрузка изображения
**POST** `/web/upload-image`
multipart/form-data: `file` (image)
**Response:**
```json
{
  "success": true,
  "file_path": "uploads/20260128_120000_abcd1234.jpg",
  "message": "Image uploaded successfully",
  "file_size": 123456
}
```
**Ошибки:**
```json
{
  "detail": "Invalid file format. Allowed: .jpg, .jpeg, .png, .gif, .webp"
}
```
```json
{
  "detail": "File too large. Maximum size: 10 MB"
}
```

---

## 5. Получение списка агентов
**GET** `/agents`
**Response:**
```json
[
  {
    "id": 1,
    "name": "FishCare Vision",
    "slug": "fishcare-vision",
    "description": "Vision agent for fish analysis",
    "is_active": true,
    "version": "1.0"
  }
]
```

---

## 6. Получение возможностей агента
**GET** `/agents/capabilities`
**Response:**
```json
{
  "agent_id": 1,
  "agent_name": "FishCare Vision",
  "supports_text": true,
  "supports_vision": true
}
```

---

## 7. Отправка запроса агенту (текст/изображение)
**POST** `/agents/invoke`
**Request:**
```json
{
  "input": "Что с моей рыбой?",
  "image_path": "uploads/20260128_120000_abcd1234.jpg",
  "variables": {},
  "stream": false
}
```
**Response:**
```json
{
  "agent_id": 1,
  "agent_name": "FishCare Vision",
  "output": "Ваша рыба выглядит здоровой.",
  "model": "gpt-4-vision",
  "processed_image": true,
  "usage": {
    "free_remaining": 1,
    "paid_remaining": 5,
    "should_upgrade": false
  },
  "usage_tokens": 800
}
```
**Ошибки (лимиты, неподдерживаемый тип):**
```json
{
  "detail": {
    "message": "Лимит запросов исчерпан.",
    "should_upgrade": true,
    "free_remaining": 0,
    "paid_remaining": 0
  }
}
```
```json
{
  "detail": "This agent can only process images. Text queries are not supported."
}
```

---

## 8. Получение биллинга и тарифов
**GET** `/billing/account` — текущий тариф, лимиты, статус
**GET** `/billing/usage?days=30` — статистика использования
**GET** `/billing/activity?limit=20&days=30` — история активности
**GET** `/billing/usage-records?limit=50&days=30` — детальный лог
**GET** `/billing/plans` — все тарифы
**GET** `/billing/plans/available` — тарифы, доступные для покупки

**Примеры всех полей см. ниже:**
```json
{
  "organization_id": 1,
  "plan_id": 2,
  "plan_name": "Pro Subscription",
  "plan_type": "subscription",
  "plan_type_display": "Подписка",
  "plan_interval": "monthly",
  "status": "active",
  "status_display": "Активна",
  "balance": 0.0,
  "total_spent": 19.99,
  "free_requests_limit": 3,
  "free_requests_used": 2,
  "free_requests_remaining": 1,
  "free_trial_days": 7,
  "trial_started_at": "2024-01-01T12:00:00Z",
  "trial_end_date": "2024-01-08T12:00:00Z",
  "subscription_start_date": "2024-01-01T12:00:00Z",
  "subscription_end_date": null,
  "max_requests_per_period": 30,
  "requests_used_current_period": 10,
  "requests_remaining_current_period": 20,
  "period_started_at": "2024-01-01T12:00:00Z",
  "credits_purchased": null,
  "credits_used": null,
  "credits_remaining": null,
  "paddle_subscription_id": "sub_123456",
  "next_billing_date": "2024-02-01T12:00:00Z",
  "paused_at": null,
  "cancelled_at": null,
  "can_use_service": true,
  "should_upgrade": false,
  "upgrade_reason": null
}
```

---

## 9. Смена тарифа/покупка пакета
**POST** `/billing/subscribe`
**Request:**
```json
{
  "plan_id": 2
}
```
**Response:**
```json
{
  ...BillingAccountResponse fields...,
  "checkout_url": "https://checkout.paddle.com/xyz",
  "transaction_id": "tr_123456"
}
```
**Ошибки:**
```json
{
  "detail": "You are already subscribed to this plan."
}
```

---

## 10. Отмена подписки
**POST** `/billing/cancel`
**Response:**
```json
{
  ...BillingAccountResponse fields...
}
```

---

## Примечания
- Все поля обязательны для обработки на клиенте.
- Все даты/время — ISO 8601 (UTC).
- Все ошибки возвращаются с полем `detail` (или вложенным объектом).
- Для полного флоу: регистрация → вход → получение профиля → загрузка изображения → отправка запроса агенту → получение ответа → биллинг/смена тарифа.

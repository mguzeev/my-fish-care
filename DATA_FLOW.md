# Поток данных: регистрация → биллинг → промпт

## КРАТКАЯ СХЕМА: От регистрации до вызова агента

### 1. **Регистрация**
- POST /auth/register → создается User в таблице `users`

### 2. **Настройка подписки** (админ или автоматически)
- Создается Organization в `organizations`
- User.organization_id = organization.id (связываем пользователя с организацией)
- Админ создает Agent в `agents` (например, "Sales Bot")
- Админ создает SubscriptionPlan в `subscription_plans` (например, "Monthly Plan")
- В таблицу `plan_agents` записывается связь: plan_id + agent_id (какие агенты входят в план)
- Создается BillingAccount в `billing_accounts`: organization_id + subscription_plan_id + status=ACTIVE

### 3. **Пользователь открывает dashboard**
- GET /agents → по токену находим user_id → User в `users`
- По user.organization_id → BillingAccount в `billing_accounts`
- По billing_account.subscription_plan_id → SubscriptionPlan в `subscription_plans`
- Через `plan_agents` (по plan_id) → получаем список agent_id → агенты из `agents`
- **Показываем пользователю только эти агенты в dropdown для выбора**

### 4. **Пользователь выбирает агента и вводит запрос**
- Пользователь выбирает агента из dropdown (например, agent_id=5)
- Вводит запрос "Привет" и нажимает "Send Query"
- POST /agents/5/invoke {"input": "Привет"}
- **Policy Engine проверяет доступ (дополнительная проверка на backend):**
  - User → organization_id → BillingAccount → проверяем status=ACTIVE
  - BillingAccount → subscription_plan_id → через `plan_agents` → проверяем есть ли agent_id=5
  - Если нет → 403 Forbidden "Agent not included in your plan"
- **Если доступ есть:**
  - Берем Agent из `agents` по id=5
  - Ищем PromptVersion в `prompt_versions` где agent_id=5 AND is_active=True
  - Agent Runtime подставляет input в промпт, вызывает OpenAI API
  - Возвращаем результат пользователю

### Ключевые таблицы и их связи:
```
users → organizations → billing_accounts → subscription_plans → (plan_agents) → agents → prompt_versions
```

**Таблицы:**
- `users` - пользователи системы
- `organizations` - организации (multi-tenant)
- `billing_accounts` - биллинг аккаунт организации с подпиской
- `subscription_plans` - тарифные планы
- `plan_agents` - связь планов и агентов (many-to-many)
- `agents` - AI агенты
- `prompt_versions` - версии промптов для агентов

**Важные поля связей:**
- User.organization_id → Organization.id
- BillingAccount.organization_id → Organization.id
- BillingAccount.subscription_plan_id → SubscriptionPlan.id
- plan_agents.plan_id → SubscriptionPlan.id
- plan_agents.agent_id → Agent.id
- PromptVersion.agent_id → Agent.id

---

## ДЕТАЛЬНОЕ ОПИСАНИЕ

## 1. Регистрация и идентификация
- Email/пароль: `POST /auth/register` и `POST /auth/login` создают запись `User`, хранят `hashed_password`, задают `locale` и статусы активности/верификации ([app/auth/router.py](app/auth/router.py)).
- Telegram OAuth: `POST /auth/telegram/callback` проверяет HMAC, находит или создает `User` с временными `username`/`email`, выдает пары `access_token`/`refresh_token` и редиректит на dashboard с токенами в query ([app/auth/router.py](app/auth/router.py)).
- Telegram-бот: `/start` автосоздает `User` с `telegram_id`, временным email и паролем; `/register` позволяет заменить email; `/locale` обновляет язык ([app/channels/telegram.py](app/channels/telegram.py)).
- Токены: JWT создаются в `create_access_token`/`create_refresh_token` и передаются в `Authorization: Bearer …` для защищенных эндпоинтов ([app/core/security.py](app/core/security.py)).

## 2. Организации и биллинг
- Модели: `Organization` связывает пользователей, а `BillingAccount` хранит баланс, текущий план и статусы подписки ([app/models/organization.py](app/models/organization.py), [app/models/billing.py](app/models/billing.py)).
- Получение аккаунта: `GET /billing/account` требует `organization_id` у пользователя, автосоздает `BillingAccount` при отсутствии и возвращает план/баланс/статус ([app/billing/router.py](app/billing/router.py)).
- Выбор плана: `POST /billing/subscribe` принимает `plan_id`, пишет его в `BillingAccount`, ставит статус `active`, сохраняет дату старта ([app/billing/router.py](app/billing/router.py)).
- Отмена: `POST /billing/cancel` меняет статус на `canceled` и фиксирует `subscription_end_date` ([app/billing/router.py](app/billing/router.py)).
- Webhooks Paddle: `/webhooks/paddle` обновляет статус подписки, списания и расходы по `paddle_subscription_id`/`customer_id` ([app/webhooks/router.py](app/webhooks/router.py)).

## 3. Доступ и учет использования
- Проверка активности: почти все защищенные маршруты используют `get_current_active_user`, блокируя неактивных пользователей ([app/auth/dependencies.py](app/auth/dependencies.py)).
- Политики: `PolicyEngine` поддерживает `rate_limit`/`resource_access`, но не подключен к маршрутам (нет вызовов `enforce_policy`) ([app/policy/engine.py](app/policy/engine.py)).
- Логирование usage: `UsageMiddleware` (включен вне debug) пишет `UsageRecord` с endpoint/method/status/latency и user_id, извлекая его из `Authorization` заголовка ([app/usage/tracker.py](app/usage/tracker.py), [app/models/usage.py](app/models/usage.py)).

## 4. Выбор агента и построение промпта
- Вызов: `POST /agents/{agent_id}/invoke` требует JWT, ищет активный `Agent` и объединяет `input` с доп. `variables` из тела запроса ([app/agents/router.py](app/agents/router.py)).
- Конфигурация агента: поля `Agent.system_prompt`, `Agent.prompt_template` (user-часть), `model_name`, `temperature`, `max_tokens` лежат в БД ([app/models/agent.py](app/models/agent.py)).
- Рендер промпта: `AgentRuntime._build_prompt` создает `PromptTemplate` с обязательной переменной `input`, подставляет данные и формирует сообщения system+user ([app/agents/runtime.py](app/agents/runtime.py), [app/prompts/models.py](app/prompts/models.py)).
- Отправка в LLM: `AgentRuntime._completion` / `_stream_completion` вызывает OpenAI Chat Completions с выбранной моделью и лимитами из настроек ([app/agents/runtime.py](app/agents/runtime.py), [app/core/config.py](app/core/config.py)).

## 5. Сквозной сценарий (данные и статусы)
1) Пользователь регистрируется (email/пароль или Telegram) → создается `users` запись; при OAuth Telegram сразу выдаются токены.  
2) Пользователь логинится → получает JWT, необходимый для биллинга и вызова агентов.  
3) (Опционально) Привязка к организации и выбор плана через `/billing/subscribe`; состояние подписки обновляют webhooks Paddle.  
4) Пользователь вызывает `/agents/{id}/invoke` с `input`; сервер подтягивает конфиг агента из БД, рендерит промпт, отправляет в LLM и возвращает completion (или stream).  
5) UsageMiddleware (в прод-среде) фиксирует факт вызова и метрики в `usage_records`, связывая с `user_id`.

## 6. От чего зависит итоговый промпт
- От выбранного `agent_id` (system_prompt/prompt_template/версия в `agents`).
- От пользовательских переменных, переданных в `variables`, и обязательного текста `input`.
- От глобальных настроек модели в конфиге (`openai_model`, `openai_temperature`, `openai_max_tokens`).
- От локали пользователя (используется в ответах веб/телеграм-канала, но не в самом рендере промпта по умолчанию).

# Исправление дублирования транзакций и отображения истории покупок

**Дата:** 18 января 2026  
**Проблема:** Вебхуки Paddle обрабатывались дважды, транзакции не отображались пользователю

---

## 🔴 Проблема 1: Дублирование обработки транзакций

### Что было:
Paddle отправляет **два разных события** для одной транзакции:
1. `transaction.paid` (event_id: `evt_01kf8y0xtfk4krz0jkmhz50wyc`)
2. `transaction.completed` (event_id: `evt_01kf8y0zvn17qc9zrnq18c9664`)

Оба события обрабатывались через `handle_transaction_completed()`, что приводило к:
- Двойному начислению кредитов
- Пользователь платил за 1 кредит, получал 2

### Защита была неправильной:
```python
# СТАРАЯ (неработающая) проверка
if event_id and billing_account.last_webhook_event_id == event_id:
    return {"message": "Event already processed"}
```

**Проблема:** `event_id` разный для каждого события, но `transaction_id` одинаковый!

### Решение:
```python
# НОВАЯ (правильная) проверка
if transaction_id and billing_account.last_transaction_id == transaction_id:
    logger.info(f"Duplicate transaction: {transaction_id} (already processed)")
    return {"message": "Transaction already processed"}
```

**Изменения в:** [app/webhooks/router.py](app/webhooks/router.py#L521-L523)

---

## 🔴 Проблема 2: Транзакции не отображаются пользователю

### Что было:
Эндпоинт `/billing/activity` показывал только:
- ✅ Подписки (subscription started)
- ✅ Отмены подписок (subscription cancelled)
- ❌ **Не показывал ONE_TIME покупки**

Пользователь видел логи покупки в системе, но не видел в своей истории активности.

### Решение 1: История покупок в БД

Добавлена запись в таблицу `one_time_purchases` при обработке вебхука:

```python
# Create purchase history record
from app.models.billing import OneTimePurchase
purchase = OneTimePurchase(
    billing_account_id=billing_account.id,
    plan_id=plan.id,
    credits_purchased=plan.one_time_limit or 0,
    price_paid=total_amount,
    currency=currency,
    paddle_transaction_id=transaction_id,
    created_at=datetime.utcnow()
)
db.add(purchase)
```

**Изменения в:** [app/webhooks/router.py](app/webhooks/router.py#L563-L575)

### Решение 2: Отображение в activity feed

Добавлен запрос one-time покупок в `/billing/activity`:

```python
# Add one-time purchase events
from app.models.billing import OneTimePurchase
purchases_result = await db.execute(
    select(OneTimePurchase)
    .where(
        (OneTimePurchase.billing_account_id == billing_account.id)
        & (OneTimePurchase.created_at >= start_date)
    )
    .order_by(desc(OneTimePurchase.created_at))
)

for purchase in purchases_result.scalars().all():
    # Get plan name
    plan_name = "Unknown Pack"
    if purchase.plan_id:
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == purchase.plan_id)
        )
        plan = plan_result.scalar_one_or_none()
        if plan:
            plan_name = plan.name
    
    events.append(ActivityEventResponse(
        id=f"purchase_{purchase.id}",
        type="purchase",
        title="🛒 Credits Purchased",
        description=f"Bought {purchase.credits_purchased} credits • {plan_name}",
        cost=purchase.price_paid,
        created_at=purchase.created_at
    ))
```

**Изменения в:** [app/billing/router.py](app/billing/router.py#L631-L659)

---

## ✅ Результат

### Защита от дублей:
- ✅ Проверка по `transaction_id` вместо `event_id`
- ✅ Повторные события игнорируются с логом: `Duplicate transaction: txn_xxx (already processed)`
- ✅ Кредиты начисляются ровно один раз

### История покупок:
- ✅ Все ONE_TIME покупки сохраняются в `one_time_purchases`
- ✅ Пользователь видит историю в `/billing/activity`
- ✅ Отображается: количество кредитов, название пакета, цена
- ✅ Иконка 🛒 для покупок, 💳 для подписок, ❌ для отмен

### Логи в production:
```
2026-01-18 16:11:48 - Transaction completed: id=txn_01kf8y02cab8cx4t5zscvat97s
2026-01-18 16:11:48 - One-time purchase completed: customer=ctm_..., plan=9 (one time 20e 1 day)
2026-01-18 16:11:48 - Incremented one_time_purchases_count to 1
2026-01-18 16:11:48 - Created purchase history record for transaction txn_...

2026-01-18 16:11:50 - Transaction completed: id=txn_01kf8y02cab8cx4t5zscvat97s
2026-01-18 16:11:50 - Duplicate transaction: txn_01kf8y02cab8cx4t5zscvat97s (already processed)
```

---

## 📝 Файлы изменены:

1. **[app/webhooks/router.py](app/webhooks/router.py)**
   - Добавлен импорт `Decimal`
   - Исправлена проверка дублей (transaction_id вместо event_id)
   - Добавлено создание записи `OneTimePurchase`
   - Извлечение цены и валюты из webhook payload

2. **[app/billing/router.py](app/billing/router.py)**
   - Добавлен запрос one-time покупок в `/billing/activity`
   - Формирование событий типа "purchase" с деталями
   - Отображение количества кредитов и названия плана
   - **Кредиты показываются ВСЕГДА** (если > 0), независимо от типа плана
   - Обновлена логика `can_use_service` с приоритетной проверкой

3. **[app/templates/dashboard.html](app/templates/dashboard.html)**
   - Добавлена переменная `creditsInfo` для отображения кредитов
   - Кредиты показываются **для любого типа плана** (комбинированная модель)
   - Иконка 🛒 для визуального выделения кредитов
   - Порядок отображения: Plan → Type → Status → **Credits** → Free Requests → Time Info

4. **[UX_AUDIT_REGISTRATION_AND_BILLING.md](UX_AUDIT_REGISTRATION_AND_BILLING.md)**
   - Обновлена документация webhook логики
   - Добавлено описание защиты от дублей
   - Обновлен список "Что работает хорошо"
   - Добавлены решённые проблемы #4 и #5

---

## 🚀 Деплой

Для применения изменений:

```bash
# Перезапустить сервис
sudo systemctl restart bot-generic

# Проверить логи
sudo journalctl -u bot-generic -f
```

---

## 🧪 Как протестировать:

1. Создать тестовую ONE_TIME покупку через Paddle Sandbox
2. Проверить логи - должен быть только один `Incremented one_time_purchases_count`
3. Открыть `/billing/activity` - покупка должна отображаться
4. Проверить БД: `SELECT * FROM one_time_purchases ORDER BY created_at DESC LIMIT 1`

---

## 🔴 Проблема 3: Кредиты не отображались при SUBSCRIPTION плане

### Что было:
Пользователь с планом **SUBSCRIPTION** купил **2 кредита** (one-time покупки), но они **не отображались** в UI:
- В БД: `one_time_purchases_count = 4`, `one_time_requests_used = 2`
- Доступно: 2 кредита
- На странице биллинга: показывались только Free Requests: 3/5
- Кредиты не показывались вообще!

### Причина:
В коде API `/billing/account` кредиты показывались **только если план ONE_TIME**:

```python
# СТАРЫЙ КОД (неправильный)
if is_one_time:  # <--- Кредиты только для ONE_TIME планов!
    credits_purchased = ba.one_time_purchases_count
    credits_used = ba.one_time_requests_used
    credits_remaining = max(0, credits_purchased - credits_used)
```

Но согласно **комбинированной модели**, пользователь может иметь:
- SUBSCRIPTION план (основной)
- + докупленные ONE_TIME кредиты (дополнительно)

Эти ресурсы работают **одновременно** и должны **оба отображаться**!

### Решение:

**Изменение 1:** Показывать кредиты всегда (если они есть):

```python
# НОВЫЙ КОД (правильный)
# Кредиты (ONE_TIME) - показываем ВСЕГДА если они есть (комбинированная модель)
# Пользователь может иметь SUBSCRIPTION план И докупленные кредиты одновременно
credits_purchased = ba.one_time_purchases_count if ba.one_time_purchases_count > 0 else None
credits_used = ba.one_time_requests_used if ba.one_time_purchases_count > 0 else None
credits_remaining = max(0, ba.one_time_purchases_count - ba.one_time_requests_used) if ba.one_time_purchases_count > 0 else None
```

**Изменение 2:** Обновить логику `can_use_service` с приоритетной проверкой:

```python
# Приоритетная проверка (комбинированная модель):
# 1. Сначала проверяем ONE_TIME кредиты (работают для ЛЮБОГО плана)
# 2. Потом проверяем бесплатные запросы
# 3. Потом лимиты SUBSCRIPTION

# Проверка 1: ONE_TIME кредиты (если есть)
if credits_remaining and credits_remaining > 0:
    can_use = True
# Проверка 2: Бесплатные запросы
elif free_remaining > 0:
    can_use = True
# Проверка 3: Лимиты подписки (только для SUBSCRIPTION планов)
elif is_subscription and remaining_period and remaining_period > 0:
    can_use = True
else:
    # Все ресурсы исчерпаны
    should_upgrade = True
    upgrade_reason = "Лимит запросов исчерпан. Купите пакет кредитов или перейдите на более высокий тариф."
```

**Изменения в:** [app/billing/router.py](app/billing/router.py#L240-L287)

---

## ✅ Результат обновления

### Отображение кредитов:
- ✅ Кредиты показываются **всегда**, если `one_time_purchases_count > 0`
- ✅ Работает для **любого** типа плана (SUBSCRIPTION или ONE_TIME)
- ✅ API возвращает: `credits_purchased`, `credits_used`, `credits_remaining`

### Комбинированная модель полностью работает:
```json
{
  "plan_name": "FREE 5 requests",
  "plan_type": "subscription",
  "status": "trialing",
  
  "free_requests_limit": 5,
  "free_requests_used": 2,
  "free_requests_remaining": 3,
  
  "credits_purchased": 4,        // <- Теперь показываются!
  "credits_used": 2,              // <- Теперь показываются!
  "credits_remaining": 2,         // <- Теперь показываются!
  
  "can_use_service": true,
  "upgrade_reason": null
}
```

### Пользователь видит:
- ✅ **SUBSCRIPTION план:** FREE 5 requests (статус: Trial Period)
- ✅ **Бесплатные запросы:** 3 / 5
- ✅ **Кредиты:** 2 / 4 (или прогресс-бар с оставшимися кредитами)
- ✅ **История покупок** в `/billing/activity`: 2 транзакции по 1 кредиту

---

**Статус:** ✅ Готово к деплою

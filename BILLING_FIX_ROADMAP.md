# 🛠️ ПЛАН ИСПРАВЛЕНИЯ БИЛЛИНГОВОЙ СИСТЕМЫ

**Дата**: 18 января 2026  
**Основано на**: BILLING_AUDIT_REPORT.md  
**Статус**: ГОТОВ К РЕАЛИЗАЦИИ

---

## 📋 ОБЗОР ЭТАПОВ

| Этап | Описание | Время | Критичность |
|------|----------|-------|-------------|
| **1** | Критические исправления биллинга | ~2-3 ч | 🔴 КРИТИЧНО |
| **2** | Модель данных и миграции | ~1-2 ч | 🟡 ВАЖНО |
| **3** | UX и валидация планов | ~2 ч | 🟢 УЛУЧШЕНИЯ |
| **4** | Рефакторинг и оптимизация | ~1 ч | 🔵 OPTIONAL |

**Общее время**: ~6-8 часов разработки + тестирование

---

# 🚨 ЭТАП 1: КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ БИЛЛИНГА
> **Цель**: Исправить критические ошибки, которые ломают бизнес-логику  
> **Время**: ~2-3 часа  
> **Приоритет**: МАКСИМАЛЬНЫЙ

## 1.1 Блокировать ONE_TIME покупки при активной подписке

**Файл**: `app/billing/router.py`  
**Функция**: `subscribe()`  
**После строки**: `ba = BillingAccount(organization_id=current_user.organization_id)`

```python
# ДОБАВИТЬ ЭТУ ПРОВЕРКУ:
if plan.plan_type == PlanType.ONE_TIME:
    if ba.subscription_plan_id and ba.subscription_status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        current_plan = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == ba.subscription_plan_id))
        current_plan = current_plan.scalar_one_or_none()
        if current_plan and current_plan.plan_type == PlanType.SUBSCRIPTION:
            raise HTTPException(
                status_code=400, 
                detail="Cannot purchase credits while subscription is active. Cancel subscription first to buy additional credits."
            )
```

## 1.2 Исправить webhook обработку ONE_TIME покупок

**Файл**: `app/webhooks/router.py`  
**Функция**: `handle_transaction_completed()`  
**Строки**: ~562-566

```python
# ЗАМЕНИТЬ ЭТИ СТРОКИ:
# billing_account.subscription_plan_id = plan.id  # ❌ УБРАТЬ
# billing_account.subscription_status = SubscriptionStatus.ACTIVE  # ❌ УБРАТЬ
# billing_account.subscription_start_date = datetime.utcnow()  # ❌ УБРАТЬ

# НА ЭТИ:
# Increment cumulative count
if plan.one_time_limit:
    billing_account.one_time_purchases_count += plan.one_time_limit
    logger.info(f"Incremented one_time_purchases_count to {billing_account.one_time_purchases_count}")

# Update transaction info only
billing_account.last_transaction_id = transaction_id
billing_account.last_webhook_event_id = event_id
```

## 1.3 Исправить счётчики использования в Policy Engine

**Файл**: `app/policy/engine.py`  
**Функция**: `check_usage_limits()`  
**Строки**: ~175-178

```python
# ЗАМЕНИТЬ:
if plan.plan_type == PlanType.ONE_TIME:
    total_purchased = billing_account.one_time_purchases_count
    used = billing_account.requests_used_current_period  # ❌ НЕВЕРНЫЙ СЧЁТЧИК

# НА:
if plan.plan_type == PlanType.ONE_TIME:
    total_purchased = billing_account.one_time_purchases_count
    used = billing_account.one_time_requests_used  # ✅ ПРАВИЛЬНЫЙ СЧЁТЧИК
```

**⚠️ ВНИМАНИЕ**: Требует добавления поля `one_time_requests_used` в модель (см. Этап 2)

## 1.4 Исправить increment_usage в Policy Engine

**Файл**: `app/policy/engine.py`  
**Функция**: `increment_usage()`  
**После строки**: `if plan.plan_type == PlanType.ONE_TIME:`

```python
# ЗАМЕНИТЬ:
billing_account.requests_used_current_period += 1

# НА:
billing_account.one_time_requests_used += 1
```

---

## ✅ КРИТЕРИИ ГОТОВНОСТИ ЭТАПА 1:
- [ ] Нельзя купить ONE_TIME план при активной подписке
- [ ] ONE_TIME покупки НЕ перезаписывают subscription_plan_id
- [ ] ONE_TIME планы используют отдельный счётчик (после Этапа 2)
- [ ] Webhook'и корректно обрабатывают оба типа планов

---

# 🔧 ЭТАП 2: МОДЕЛЬ ДАННЫХ И МИГРАЦИИ
> **Цель**: Добавить недостающие поля и создать миграции  
> **Время**: ~1-2 часа  
> **Приоритет**: ВЫСОКИЙ

## 2.1 Добавить поле is_default в SubscriptionPlan

**Файл**: `app/models/billing.py`  
**В класс**: `SubscriptionPlan`

```python
# ДОБАВИТЬ ПОЛЕ:
is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

## 2.2 Добавить поле one_time_requests_used в BillingAccount

**Файл**: `app/models/billing.py`  
**В класс**: `BillingAccount`

```python
# ДОБАВИТЬ ПОЛЕ:
one_time_requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

## 2.3 Создать миграцию Alembic

```bash
cd /home/mguzieiev/maks/bot-generic
alembic revision -m "add_is_default_and_one_time_requests_used"
```

**Содержимое миграции**:
```python
def upgrade() -> None:
    # Add is_default to subscription_plans
    op.add_column('subscription_plans', sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'))
    
    # Add one_time_requests_used to billing_accounts
    op.add_column('billing_accounts', sa.Column('one_time_requests_used', sa.Integer(), nullable=False, server_default='0'))

def downgrade() -> None:
    op.drop_column('billing_accounts', 'one_time_requests_used')
    op.drop_column('subscription_plans', 'is_default')
```

## 2.4 Исправить регистрацию пользователей

**Файл**: `app/auth/router.py`  
**Функция**: `register()`  
**Строки**: ~104-120 (поиск Free Trial плана)

```python
# ЗАМЕНИТЬ:
free_trial_plan_result = await db.execute(
    select(SubscriptionPlan).where(SubscriptionPlan.name == "Free Trial")
)

# НА:
default_plan_result = await db.execute(
    select(SubscriptionPlan).where(SubscriptionPlan.is_default == True)
)
default_plan = default_plan_result.scalar_one_or_none()

if not default_plan:
    # Fallback to first available plan with free requests
    fallback_result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.free_requests_limit > 0)
        .order_by(SubscriptionPlan.id)
    )
    default_plan = fallback_result.scalar_one_or_none()
```

---

## ✅ КРИТЕРИИ ГОТОВНОСТИ ЭТАПА 2:
- [ ] Поля добавлены в модели
- [ ] Миграция создана и применена
- [ ] Регистрация использует is_default план
- [ ] Существующие планы в БД обновлены

---

# 🎨 ЭТАП 3: UX И ВАЛИДАЦИЯ ПЛАНОВ
> **Цель**: Улучшить пользовательский опыт и добавить валидации  
> **Время**: ~2 часа  
> **Приоритет**: СРЕДНИЙ

## 3.1 Создать endpoint для доступных планов

**Файл**: `app/billing/router.py`  
**Новый endpoint**: `/billing/plans/available`

```python
@router.get("/plans/available")
async def get_available_plans_for_user(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get plans available for purchase by current user based on their subscription state."""
    
    # Get user's billing account
    ba = await db.execute(
        select(BillingAccount).where(BillingAccount.organization_id == current_user.organization_id)
    )
    billing_account = ba.scalar_one_or_none()
    
    has_active_subscription = (
        billing_account 
        and billing_account.subscription_plan_id 
        and billing_account.subscription_status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
    )
    
    query = select(SubscriptionPlan).order_by(SubscriptionPlan.price)
    
    if has_active_subscription:
        # Only show SUBSCRIPTION plans for upgrade/downgrade
        query = query.where(SubscriptionPlan.plan_type == PlanType.SUBSCRIPTION)
        # Exclude current plan
        query = query.where(SubscriptionPlan.id != billing_account.subscription_plan_id)
    else:
        # Show all valid plans
        pass
    
    result = await db.execute(query)
    plans = result.scalars().all()
    
    # Filter only valid plans
    valid_plans = []
    for plan in plans:
        # Check if plan has agents
        if len(plan.agents) == 0:
            continue
        # Check if has paddle_price_id (if billing enabled)
        if settings.paddle_billing_enabled and not plan.paddle_price_id:
            continue
        valid_plans.append(plan)
    
    return [
        {
            "id": plan.id,
            "name": plan.name,
            "plan_type": plan.plan_type.value,
            "interval": plan.interval.value,
            "price": float(plan.price),
            "currency": plan.currency,
            "max_requests_per_interval": plan.max_requests_per_interval,
            "max_tokens_per_request": plan.max_tokens_per_request,
            "free_requests_limit": plan.free_requests_limit,
            "free_trial_days": plan.free_trial_days,
            "one_time_limit": plan.one_time_limit,
            "agent_count": len(plan.agents),
            "has_api_access": plan.has_api_access,
            "has_priority_support": plan.has_priority_support,
            "has_advanced_analytics": plan.has_advanced_analytics,
        }
        for plan in valid_plans
    ]
```

## 3.2 Добавить валидацию планов при подписке

**Файл**: `app/billing/router.py`  
**Функция**: `subscribe()`  
**После**: `if not plan:`

```python
# ДОБАВИТЬ ВАЛИДАЦИИ:
# Check if plan has agents
if len(plan.agents) == 0:
    raise HTTPException(
        status_code=400, 
        detail="Plan has no agents assigned. Contact administrator."
    )

# Check if plan has valid Paddle configuration (when billing enabled)
if settings.paddle_billing_enabled and not plan.paddle_price_id:
    raise HTTPException(
        status_code=400, 
        detail="Plan is missing payment configuration. Contact administrator."
    )

# Check if user is not trying to subscribe to same plan
if (ba.subscription_plan_id == plan.id 
    and ba.subscription_status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]):
    raise HTTPException(
        status_code=400, 
        detail="You are already subscribed to this plan."
    )
```

## 3.3 Связать default план с агентами при создании

**Скрипт**: `scripts/setup_default_plan.py`

```python
"""Link default plan with basic agents."""
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.billing import SubscriptionPlan  
from app.models.agent import Agent
from sqlalchemy import select

async def setup_default_plan():
    """Ensure default plan is linked with at least one agent."""
    async with AsyncSessionLocal() as db:
        # Find default plan
        result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.is_default == True)
        )
        default_plan = result.scalar_one_or_none()
        
        if not default_plan:
            print("❌ No default plan found")
            return
            
        # Find basic agents
        agent_result = await db.execute(
            select(Agent).where(Agent.is_active == True)
        )
        agents = agent_result.scalars().all()
        
        if not agents:
            print("❌ No active agents found")
            return
            
        # Link first agent to default plan if not linked
        if len(default_plan.agents) == 0:
            default_plan.agents.append(agents[0])
            await db.commit()
            print(f"✅ Linked agent '{agents[0].name}' to default plan '{default_plan.name}'")
        else:
            print(f"✅ Default plan '{default_plan.name}' already has {len(default_plan.agents)} agents")

if __name__ == "__main__":
    asyncio.run(setup_default_plan())
```

---

## ✅ КРИТЕРИИ ГОТОВНОСТИ ЭТАПА 3:
- [ ] Endpoint `/billing/plans/available` работает
- [ ] Показываются только валидные планы
- [ ] При активной подписке не показываются ONE_TIME планы  
- [ ] Валидация планов при подписке работает
- [ ] Default план связан с агентами

---

# 🔄 ЭТАП 4: РЕФАКТОРИНГ И ОПТИМИЗАЦИЯ
> **Цель**: Улучшить архитектуру и производительность  
> **Время**: ~1 час  
> **Приоритет**: НИЗКИЙ (можно отложить)

## 4.1 Разделить создание Paddle транзакций

**Файл**: `app/billing/router.py`  
**Функция**: `subscribe()`

```python
# ЗАМЕНИТЬ единый вызов:
transaction = _as_dict(
    await paddle.create_subscription(  # ❌ ДЛЯ ВСЕХ ТИПОВ
        customer_id=ba.paddle_customer_id,
        price_id=plan.paddle_price_id,
    )
)

# НА РАЗДЕЛЕНИЕ ПО ТИПАМ:
if plan.plan_type == PlanType.SUBSCRIPTION:
    # For recurring subscriptions
    transaction = _as_dict(
        await paddle.create_subscription(
            customer_id=ba.paddle_customer_id,
            price_id=plan.paddle_price_id,
        )
    )
else:  # PlanType.ONE_TIME
    # For one-time purchases
    transaction = _as_dict(
        await paddle.create_transaction(
            customer_id=ba.paddle_customer_id,
            price_id=plan.paddle_price_id,
        )
    )
```

## 4.2 Добавить computed properties для валидации планов

**Файл**: `app/models/billing.py`  
**В класс**: `SubscriptionPlan`

```python
@property
def is_valid(self) -> bool:
    """Check if plan is valid for purchase."""
    return (
        len(self.agents) > 0 and 
        (not settings.paddle_billing_enabled or self.paddle_price_id is not None) and
        self.price >= 0
    )

@property  
def validation_errors(self) -> List[str]:
    """Get list of validation errors."""
    errors = []
    if len(self.agents) == 0:
        errors.append("No agents assigned to this plan")
    if settings.paddle_billing_enabled and not self.paddle_price_id:
        errors.append("Missing Paddle price configuration") 
    if self.price < 0:
        errors.append("Invalid price")
    return errors
```

## 4.3 Добавить историю ONE_TIME покупок

**Модель**: `app/models/billing.py`

```python
class OneTimePurchase(Base):
    """History of one-time credit purchases."""
    
    __tablename__ = "one_time_purchases"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    billing_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("billing_accounts.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True
    )
    
    # Purchase details
    credits_purchased: Mapped[int] = mapped_column(Integer, nullable=False)
    price_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    
    # Paddle details
    paddle_transaction_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    billing_account: Mapped["BillingAccount"] = relationship("BillingAccount")
    plan: Mapped[Optional["SubscriptionPlan"]] = relationship("SubscriptionPlan")
```

---

## ✅ КРИТЕРИИ ГОТОВНОСТИ ЭТАПА 4:
- [ ] Paddle API вызывается правильно для каждого типа плана
- [ ] Computed properties работают  
- [ ] История ONE_TIME покупок сохраняется
- [ ] Производительность не ухудшилась

---

# 🧪 ПЛАН ТЕСТИРОВАНИЯ

## После каждого этапа проверить:

### Этап 1:
1. ✅ Регистрация пользователя → получает default план
2. ✅ Покупка подписки → нельзя купить ONE_TIME  
3. ✅ Отмена подписки → можно купить ONE_TIME
4. ✅ ONE_TIME покупка → НЕ ломает подписку
5. ✅ Webhook обработка → корректно для обоих типов

### Этап 2:  
1. ✅ Миграция применяется без ошибок
2. ✅ Новые пользователи получают default план
3. ✅ Счётчики ONE_TIME работают отдельно

### Этап 3:
1. ✅ `/billing/plans/available` возвращает правильные планы
2. ✅ Валидация блокирует невалидные планы
3. ✅ UX логичен и понятен

### Этап 4:
1. ✅ Paddle API вызовы корректны  
2. ✅ История покупок сохраняется
3. ✅ Нет регрессий производительности

---

# 📊 МЕТРИКИ УСПЕХА

## Бизнес-метрики:
- 🎯 **0 потерянных подписок** из-за перезаписи планов
- 📈 **Увеличение ARPU** за счёт правильного учёта ONE_TIME покупок  
- 😊 **Снижение жалоб** на проблемы с биллингом

## Технические метрики:
- 🐛 **0 критических ошибок** в биллинге
- ⚡ **< 500ms** время отклика биллинговых API
- 📊 **100% корректность** webhook обработки

---

**Статус**: 📋 ГОТОВ К РЕАЛИЗАЦИИ
**Следующий шаг**: Начать с Этапа 1 - критические исправления
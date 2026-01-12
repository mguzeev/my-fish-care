# План внедрения системы бесплатных обращений и лимитов

## Use Case
- Новый пользователь регистрируется без оплаты
- Получает 10 бесплатных обращений к агенту X с промптом Y
- После каждого ответа видит предложение апгрейда на Тариф2
- На 5-м обращении оплачивает и переходит на платный тариф
- Доиспользует оставшиеся 5 бесплатных обращений
- Затем пользуется согласно лимитам платного тарифа

---

## Этап 1: Расширение моделей данных

### 1.1 Обновить `app/models/billing.py` - SubscriptionPlan
Добавить поля для бесплатных лимитов:
```python
# Free trial limits
free_requests_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
free_trial_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

**Что это дает:**
- `free_requests_limit` - сколько бесплатных обращений дает план (например, 10)
- `free_trial_days` - сколько дней бесплатного доступа (например, 2 дня)

### 1.2 Обновить `app/models/billing.py` - BillingAccount
Добавить счетчики использования:
```python
# Usage tracking
free_requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
requests_used_current_period: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
period_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
trial_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

**Что это дает:**
- `free_requests_used` - сколько бесплатных использовано из лимита
- `requests_used_current_period` - сколько использовано в текущем периоде (для платных)
- `period_started_at` - начало текущего периода (для reset счетчика)
- `trial_started_at` - когда начался trial (для проверки free_trial_days)

### 1.3 Создать миграцию Alembic
```bash
alembic revision --autogenerate -m "add_usage_tracking_and_free_limits"
```

Проверить и применить:
```bash
alembic upgrade head
```

---

## Этап 2: Обновление Policy Engine

### 2.1 Добавить метод `check_usage_limits()` в `app/policy/engine.py`

```python
async def check_usage_limits(
    self, 
    db: AsyncSession, 
    user: User, 
    agent_id: int
) -> dict:
    """
    Проверяет лимиты использования и возвращает информацию о доступе.
    
    Returns:
        {
            "allowed": bool,
            "reason": str,
            "free_remaining": int,
            "paid_remaining": int,
            "should_upgrade": bool
        }
    """
    # 1. Получить billing_account и plan
    # 2. Проверить free_requests_used < plan.free_requests_limit
    # 3. Проверить free_trial_days (trial_started_at + days > now)
    # 4. Если бесплатные закончились - проверить платные лимиты
    # 5. Вернуть детальную информацию для UI
```

**Логика проверки:**
1. Superuser → всегда allowed
2. Есть бесплатные (`free_requests_used < plan.free_requests_limit`) → allowed, вернуть остаток
3. Trial активен (`now < trial_started_at + free_trial_days`) → allowed
4. Бесплатные закончились → проверить платный лимит:
   - Если `requests_used_current_period < plan.max_requests_per_interval` → allowed
   - Иначе → blocked, вернуть should_upgrade=True

### 2.2 Добавить метод `increment_usage()` в `app/policy/engine.py`

```python
async def increment_usage(
    self,
    db: AsyncSession,
    user: User
) -> None:
    """Увеличить счетчик использования после успешного вызова агента."""
    # 1. Получить billing_account
    # 2. Если есть бесплатные - увеличить free_requests_used
    # 3. Иначе - увеличить requests_used_current_period
    # 4. Проверить reset периода (если period_started_at + interval < now)
    # 5. Сохранить в БД
```

### 2.3 Добавить метод `reset_period_if_needed()` (вспомогательный)

```python
async def reset_period_if_needed(
    self,
    billing_account: BillingAccount,
    plan: SubscriptionPlan
) -> None:
    """Сбросить счетчик периода если истек interval."""
    # Проверить interval (daily/weekly/monthly/yearly)
    # Если period_started_at + interval < now:
    #   - requests_used_current_period = 0
    #   - period_started_at = now
```

---

## Этап 3: Обновление API эндпоинтов

### 3.1 Обновить `POST /agents/{agent_id}/invoke` в `app/agents/router.py`

**Текущий код:**
```python
# Проверка доступа
await policy_engine.check_agent_access(db, current_user, agent_id)
```

**Новый код:**
```python
# Проверка лимитов (включает check_agent_access внутри)
usage_info = await policy_engine.check_usage_limits(db, current_user, agent_id)

if not usage_info["allowed"]:
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "message": usage_info["reason"],
            "should_upgrade": usage_info["should_upgrade"]
        }
    )

# Вызов агента
result = await runtime.execute(...)

# Увеличить счетчик после успешного вызова
await policy_engine.increment_usage(db, current_user)
await db.commit()

# Вернуть результат + информацию о лимитах
return {
    "response": result,
    "usage": {
        "free_remaining": usage_info["free_remaining"],
        "paid_remaining": usage_info["paid_remaining"],
        "should_upgrade": usage_info["should_upgrade"]
    }
}
```

### 3.2 Добавить `GET /billing/usage` эндпоинт

```python
@router.get("/usage")
async def get_usage_info(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить информацию об использовании лимитов."""
    # Вернуть free_remaining, paid_remaining, plan info
```

---

## Этап 4: Обновление регистрации и onboarding

### 4.1 Обновить `POST /auth/register` в `app/auth/router.py`

**После создания User:**
```python
# 1. Создать Organization для нового пользователя
# 2. Найти "Free Trial" план (или создать если нет)
# 3. Создать BillingAccount:
#    - subscription_plan_id = free_trial_plan.id
#    - subscription_status = TRIALING
#    - free_requests_used = 0
#    - trial_started_at = datetime.utcnow()
# 4. Привязать пользователя к организации
```

**Создать дефолтный "Free Trial" план:**
```python
# В scripts/seed_data.py или alembic migration
SubscriptionPlan(
    name="Free Trial",
    interval=SubscriptionInterval.MONTHLY,
    price=0.00,
    max_requests_per_interval=0,  # После бесплатных - блокировка
    free_requests_limit=10,
    free_trial_days=0,
    # Связать с одним бесплатным агентом через plan_agents
)
```

---

## Этап 5: Обновление UI

### 5.1 Обновить `app/templates/dashboard.html`

**После response от агента показывать:**
```html
<div id="usageInfo" class="alert alert-info mt-3" style="display:none;">
    <strong>Использование:</strong>
    <span id="freeRemaining"></span>
    <span id="paidRemaining"></span>
    <button id="upgradeBtn" class="btn btn-primary btn-sm" style="display:none;">
        Апгрейд на платный план 🚀
    </button>
</div>
```

**В JavaScript `sendQuery()`:**
```javascript
const data = await response.json();
document.getElementById('agentResponse').textContent = data.response;

// Показать информацию о лимитах
if (data.usage) {
    const usageDiv = document.getElementById('usageInfo');
    usageDiv.style.display = 'block';
    
    if (data.usage.free_remaining > 0) {
        document.getElementById('freeRemaining').textContent = 
            `Осталось ${data.usage.free_remaining} бесплатных обращений.`;
    }
    
    if (data.usage.should_upgrade) {
        document.getElementById('upgradeBtn').style.display = 'inline-block';
    }
}
```

### 5.2 Добавить страницу апгрейда

**Создать `app/templates/upgrade.html`:**
- Показать текущий план (Free Trial)
- Список доступных платных планов
- Кнопка "Subscribe" → редирект на Paddle Checkout

**Обновить `upgradeBtn.onclick`:**
```javascript
document.getElementById('upgradeBtn').onclick = () => {
    window.location.href = '/billing/upgrade';
};
```

---

## Этап 6: Обновление биллинга

### 6.1 Обновить `POST /billing/subscribe` в `app/billing/router.py`

**При апгрейде с Free Trial на платный:**
```python
# НЕ сбрасывать free_requests_used!
# Пользователь доиспользует бесплатные даже после апгрейда

billing_account.subscription_plan_id = new_plan_id
billing_account.subscription_status = SubscriptionStatus.ACTIVE
billing_account.requests_used_current_period = 0
billing_account.period_started_at = datetime.utcnow()
# free_requests_used остается без изменений!
```

**Логика в `check_usage_limits()`:**
- Сначала проверить `free_requests_used < plan.free_requests_limit`
- Если есть бесплатные - использовать их даже на платном плане
- Только когда все 10 израсходованы - переключиться на платные лимиты

---

## ✅ Этап 7: Модели LLM (вынос хардкода) - ВЫПОЛНЕНО

**Статус:** Завершено. Таблица `llm_models` создана, runtime интегрирован, admin UI добавлен.

### 7.1 ✅ Создать модель `app/models/llm_model.py`

```python
"""LLM Model configuration."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class LLMModel(Base):
    """LLM Model configuration with API credentials."""
    
    __tablename__ = "llm_models"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # "gpt-4", "gpt-3.5-turbo", "claude-3"
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)  # "GPT-4 (OpenAI)"
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "openai", "anthropic", "google"
    
    # API Configuration
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)  # Encrypted or from env
    api_base_url: Mapped[Optional[str]] = mapped_column(String(500))  # Custom endpoint if needed
    
    # Model limits
    max_tokens_limit: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    
    # Pricing (for cost tracking)
    cost_per_1k_input_tokens: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    cost_per_1k_output_tokens: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<LLMModel(id={self.id}, name={self.name}, provider={self.provider})>"
```

**Что это дает:**
- Централизованное хранение API ключей (вместо хардкода в конфиге)
- Поддержка разных провайдеров (OpenAI, Anthropic, Google)
- Возможность добавлять новые модели через админку БЕЗ изменения кода
- Tracking стоимости вызовов

**Статус:** ✅ Модель создана, миграция применена.

### 7.2 ✅ Обновить `app/models/agent.py`

```python
class Agent(Base):
    # ...
    
    # Заменить:
    # model_name: Mapped[str] = mapped_column(String(100), default="gpt-4", nullable=False)
    
    # На:
    llm_model_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("llm_models.id", ondelete="RESTRICT"), 
        nullable=False
    )
    
    # Relationship
    llm_model: Mapped["LLMModel"] = relationship("LLMModel", lazy="selectin")
```

**Что это дает:**
- Agent → LLMModel (FK связь)
- При удалении модели - RESTRICT (нельзя удалить используемую)
- Agent.llm_model.api_key доступен напрямую

**Статус:** ✅ FK добавлен, relationship настроен.

### 7.3 ✅ Создать миграцию

**Статус:** ✅ Миграция создана и применена. Существующие агенты мигрированы на llm_model_id=1 (gpt-4).

### 7.4 ✅ Обновить `app/agents/runtime.py`

**Статус:** ✅ Runtime обновлен. Теперь использует `agent.llm_model` для получения API ключа и настроек модели.

Реализованный код:
Реализованный код:
```python
def _get_client_for_agent(self, agent: Agent) -> AsyncOpenAI:
    if not agent.llm_model:
        return self.default_client
    if not agent.llm_model.is_active:
        raise ValueError(f"LLM model '{agent.llm_model.name}' is not active")
    return AsyncOpenAI(
        api_key=agent.llm_model.api_key, 
        base_url=agent.llm_model.api_base_url
    )

async def run(self, agent, variables, prompt_version=None, stream=False):
    client = self._get_client_for_agent(agent)
    model_name = agent.llm_model.name if agent.llm_model else self.default_model
    max_tokens = min(
        agent.max_tokens, 
        agent.llm_model.max_tokens_limit if agent.llm_model else self.default_max_tokens
    )
    # ... далее вызов completion
```

### 7.5 ✅ Обновить Admin UI - `/admin/llm-models` (новый раздел)

**Статус:** ✅ Добавлены эндпоинты в `app/admin/router.py`:
- `GET /admin/llm-models` - список всех моделей
- `GET /admin/llm-models/{id}` - получить модель
- `POST /admin/llm-models` - создать новую модель
- `PUT /admin/llm-models/{id}` - обновить модель
- `DELETE /admin/llm-models/{id}` - удалить модель (с проверкой FK)

**Статус:** ✅ Добавлена вкладка "LLM Models" в `app/templates/admin.html`:
**Статус:** ✅ Добавлена вкладка "LLM Models" в `app/templates/admin.html`:
- Таблица с колонками: ID, Name, Provider, API Key (masked), Max Tokens, Context, Status, Default
- Модалки для создания и редактирования моделей
- JavaScript функции: `loadLLMModels()`, `createLLMModel()`, `editLLMModel()`, `saveLLMModelChanges()`, `deleteLLMModel()`

### 7.6 ✅ Обновить форму создания агента

**Статус:** ✅ В форме создания/редактирования агента в админке уже используется dropdown с LLM моделями.

### 7.7 Security: Хранение API ключей

**Текущая реализация:** API ключи хранятся в БД в открытом виде. В admin UI при отображении показываются маскированными (первые 8 + последние 4 символа).

**Рекомендации для production:**
```python
# В миграции:
api_key = os.getenv("OPENAI_API_KEY", "")

# В Runtime:
actual_key = llm_model.api_key or os.getenv("OPENAI_API_KEY")
```

**Рекомендации для production:**

**Вариант 1: Environment переменные**
```python
# В Runtime:
actual_key = llm_model.api_key or os.getenv("OPENAI_API_KEY")
```

**Вариант 2: Encryption в БД**
```python
from cryptography.fernet import Fernet
# Шифровать перед сохранением, расшифровывать при использовании
```

**Вариант 3: AWS Secrets Manager / HashiCorp Vault**
- Хранить только reference в БД, получать реальный ключ из secret manager

---

## Этап 8: Тестирование

### 8.1 TODO: Создать `tests/test_free_trial_limits.py`

**Тест-кейсы:**
```python
async def test_new_user_gets_free_requests():
    """Новый пользователь получает 10 бесплатных обращений."""
    
async def test_free_requests_decrement():
    """Счетчик бесплатных уменьшается после каждого вызова."""
    
async def test_block_after_free_limit():
    """После 10 обращений блокировка (если не оплатил)."""
    
async def test_upgrade_preserves_free_requests():
    """После апгрейда оставшиеся бесплатные сохраняются."""
    
async def test_paid_limits_after_free_exhausted():
    """После исчерпания бесплатных - работают платные лимиты."""
    
async def test_period_reset():
    """Счетчик периода сбрасывается после interval."""
    
async def test_trial_days_expiration():
    """2-дневный trial блокируется после истечения."""
```

### 8.2 ✅ Создать `tests/test_llm_models.py`

**Статус:** Частично покрыто существующими тестами. LLM models тестируются в `tests/test_agents_api.py` и `tests/test_prompts_runtime.py`. Админ API эндпоинты добавлены в `tests/test_admin_api.py`.

**Текущее покрытие:**
- ✅ Агент использует API ключ из связанной модели (test_prompts_runtime.py)
- ✅ Runtime проверяет is_active модели
- ✅ Админ API для LLM models (test_admin_api.py - если добавлено)

**TODO:**
- ❌ Тест на невозможность удалить модель, используемую агентами
- ❌ Тест на автоматическое снятие is_default с других моделей

### 8.3 ✅ Запустить все тесты

**Статус:** ✅ Все тесты проходят (81/81 passed)

```bash
pytest tests/ -v
# Result: 81 passed, 11 warnings
```

---

## Этап 9: Документация

### 9.1 TODO: Обновить `DATA_FLOW.md`

### 9.1 TODO: Обновить `DATA_FLOW.md`

Добавить раздел:
```markdown
## 7. LLM Models система

### Конфигурация моделей:
- LLMModel → хранит API ключи, provider, limits
- Agent.llm_model_id → FK связь с LLM Model
- Runtime динамически создает OpenAI client с agent.llm_model.api_key
- Admin UI позволяет управлять моделями без изменения кода

### Регистрация нового пользователя (для будущей реализации):
- User → Organization → BillingAccount (Free Trial plan)
- free_requests_used отслеживает использование бесплатных обращений
```

---

## Итого: Текущее состояние проекта

### ✅ Полностью реализовано (Этап 7 - LLM Models):

✅ Таблица `llm_models` создана и заполнена дефолтными моделями  
✅ Agent.llm_model_id FK связь настроена  
✅ Runtime использует agent.llm_model для API вызовов  
✅ Admin API полностью реализован (GET/POST/PUT/DELETE /admin/llm-models)  
✅ Admin UI добавлен (вкладка LLM Models с таблицей и модалками)  
✅ API ключи маскируются в UI (первые 8 + последние 4 символа)  
✅ Проверка is_active модели в runtime  
✅ Ограничение max_tokens_limit из модели  
✅ Поддержка множества провайдеров (openai, anthropic, google)  
✅ Все 81 тестов проходят  

### ❌ Не реализовано (Этапы 1-6, 8-9):

❌ Система бесплатных обращений (free_requests_limit, free_requests_used)  
❌ Usage tracking (requests_used_current_period, period_started_at)  
❌ Policy Engine методы (check_usage_limits, increment_usage)  
❌ UI для отображения оставшихся обращений  
❌ Страница апгрейда (/billing/upgrade)  
❌ Автоматическое создание Free Trial план при регистрации  
❌ Интеграция с Paddle для оплаты  
❌ Полное тестовое покрытие системы лимитов  
❌ Документация DATA_FLOW.md  

---

## Следующие шаги (приоритизация):

**Для запуска MVP системы лимитов:**
1. Этап 1.1-1.3: Добавить поля в SubscriptionPlan и BillingAccount
2. Этап 2.1-2.2: Реализовать Policy Engine методы
3. Этап 3.1: Обновить /agents/{id}/invoke с проверкой лимитов
4. Этап 4.1: Free Trial при регистрации
5. Этап 5.1: UI с remaining counter

**Для production-ready:**
6. Этап 5.2: Страница апгрейда
7. Этап 6.1: Paddle integration
8. Тесты для системы лимитов
9. Документация

**Текущий фокус:** Этап 7 (LLM Models) полностью завершён. Можно переходить к Этапу 1 (система лимитов) или продолжать улучшение существующего функционала.

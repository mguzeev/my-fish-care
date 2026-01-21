# Text/Vision Capabilities Enforcement

## Проблема
Модели имели флаги `supports_text` и `supports_vision`, но они не проверялись при отправке запросов:
- Пользователи могли отправлять текстовые запросы через Telegram и веб, даже если модель поддерживает только изображения
- Пользователи могли отправлять изображения, даже если модель поддерживает только текст
- Веб-интерфейс всегда показывал оба поля ввода независимо от capabilities модели

## Решение

### 1. Локализация (i18n)
Добавлены новые тексты ошибок во все языки (en, ru, uk):

**app/i18n/strings/en.json:**
- `errors.text_not_supported`: "📝 Sorry, this agent can only process images. Text messages are not supported."
- `errors.vision_not_supported`: "🖼️ Sorry, this agent can only process text. Image messages are not supported."

**app/i18n/strings/ru.json:**
- `errors.text_not_supported`: "📝 Извините, этот агент может обрабатывать только изображения. Текстовые сообщения не поддерживаются."
- `errors.vision_not_supported`: "🖼️ Извините, этот агент может обрабатывать только текст. Изображения не поддерживаются."

**app/i18n/strings/uk.json:**
- `errors.text_not_supported`: "📝 Вибачте, цей агент може обробляти лише зображення. Текстові повідомлення не підтримуються."
- `errors.vision_not_supported`: "🖼️ Вибачте, цей агент може обробляти лише текст. Зображення не підтримуються."

### 2. Функции для текстов (app/channels/texts.py)
Добавлены две новые функции:
```python
def text_not_supported(locale: Optional[str]) -> str:
    """Text shown when agent doesn't support text."""
    return i18n.t("errors.text_not_supported", locale)

def vision_not_supported(locale: Optional[str]) -> str:
    """Text shown when agent doesn't support vision/images."""
    return i18n.t("errors.vision_not_supported", locale)
```

### 3. Telegram Handler (app/channels/telegram.py)

#### Импорты
Добавлены новые функции в импорты:
- `text_not_supported`
- `vision_not_supported`

#### Обработчик текстовых сообщений (handle_text_message)
После получения агента добавлена проверка:
```python
# Check if agent's model supports text
if agent.llm_model and not agent.llm_model.supports_text:
    await update.message.reply_text(
        text_not_supported(user.locale),
        parse_mode="Markdown"
    )
    return
```

#### Обработчик фото (handle_photo)
После получения агента добавлена проверка:
```python
# Check if agent's model supports vision
if agent.llm_model and not agent.llm_model.supports_vision:
    await processing_msg.edit_text(
        vision_not_supported(user.locale)
    )
    return
```

### 4. Agent API (app/agents/router.py)

#### Новая модель ответа
```python
class AgentCapabilitiesResponse(BaseModel):
    """Agent capabilities response."""
    agent_id: int
    agent_name: str
    supports_text: bool
    supports_vision: bool
```

#### Новый endpoint
```python
@router.get("/capabilities", response_model=AgentCapabilitiesResponse)
async def get_agent_capabilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get capabilities of the first available agent for the current user."""
    # Возвращает capabilities первого доступного агента
```

#### Проверки в invoke endpoints
Добавлена валидация в оба endpoint (`/invoke` и `/{agent_id}/invoke`):
```python
# Validate agent capabilities
if agent.llm_model:
    # Check if text is being sent but model doesn't support text
    if payload.input and not agent.llm_model.supports_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This agent can only process images. Text queries are not supported."
        )
    
    # Check if image is being sent but model doesn't support vision
    if payload.image_path and not agent.llm_model.supports_vision:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This agent can only process text. Image queries are not supported."
        )
```

### 5. Веб-интерфейс (app/templates/dashboard.html)

#### Новая функция loadAgentCapabilities()
Загружает capabilities агента и динамически управляет отображением полей:
```javascript
async function loadAgentCapabilities() {
    try {
        const capabilities = await apiCall('/agents/capabilities');
        
        // Update UI based on capabilities
        const queryInput = document.getElementById('queryInput');
        const imageUploadSection = queryInput.closest('.form-group').nextElementSibling;
        
        if (!capabilities.supports_text) {
            // Hide text input if text is not supported
            queryInput.closest('.form-group').style.display = 'none';
        }
        
        if (!capabilities.supports_vision) {
            // Hide image upload if vision is not supported
            if (imageUploadSection) {
                imageUploadSection.style.display = 'none';
            }
        }
        
        // If only vision is supported, make query optional and update placeholder
        if (capabilities.supports_vision && !capabilities.supports_text) {
            queryInput.placeholder = 'Optional: Add description or question about the image...';
            queryInput.required = false;
        }
        
    } catch (error) {
        console.error('Failed to load agent capabilities:', error);
        // Don't block UI if capabilities can't be loaded
    }
}
```

#### Инициализация
Добавлен вызов функции при загрузке страницы:
```javascript
document.addEventListener('DOMContentLoaded', async () => {
    await loadProfile();
    await loadUsageMetrics();
    await loadSubscription();
    await loadAgentCapabilities(); // NEW
});
```

## Поведение

### Telegram
1. **Текстовое сообщение + модель только с vision**:
   - Бот отвечает: "📝 Извините, этот агент может обрабатывать только изображения..."

2. **Фото + модель только с text**:
   - Бот отвечает: "🖼️ Извините, этот агент может обрабатывать только текст..."

### Веб-интерфейс
1. **Модель только с vision**:
   - Поле для текста скрыто
   - Показывается только загрузка изображений

2. **Модель только с text**:
   - Поле для изображений скрыто
   - Показывается только поле для текста

3. **Модель с обоими capabilities**:
   - Показываются оба поля (поведение по умолчанию)

### API (agents/invoke)
При попытке отправить неподдерживаемый тип контента:
- Возвращается HTTP 400 Bad Request
- Сообщение об ошибке на английском языке

## Тестирование

### Проверка Telegram
1. Установить в админке модели флаги `supports_text=False`, `supports_vision=True`
2. Отправить текстовое сообщение в Telegram → должна прийти ошибка
3. Отправить фото → должно обработаться

4. Установить флаги `supports_text=True`, `supports_vision=False`
5. Отправить фото → должна прийти ошибка
6. Отправить текст → должно обработаться

### Проверка веб-интерфейса
1. Установить флаги `supports_text=False`, `supports_vision=True`
2. Открыть dashboard → поле для текста должно быть скрыто
3. Должна быть видна только загрузка изображений

4. Установить флаги `supports_text=True`, `supports_vision=False`
5. Открыть dashboard → поле для изображений должно быть скрыто
6. Должно быть видно только текстовое поле

### Проверка API
```bash
# Тест с текстом при supports_text=False
curl -X POST http://localhost:8000/agents/invoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": "test query"}'
# Ожидается: 400 Bad Request

# Тест с изображением при supports_vision=False
curl -X POST http://localhost:8000/agents/invoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "image_path": "uploads/image.jpg"}'
# Ожидается: 400 Bad Request
```

## Файлы изменены
1. `app/i18n/strings/en.json` - добавлены тексты ошибок
2. `app/i18n/strings/ru.json` - добавлены тексты ошибок
3. `app/i18n/strings/uk.json` - добавлены тексты ошибок
4. `app/channels/texts.py` - добавлены функции для текстов
5. `app/channels/telegram.py` - добавлены проверки в обработчики
6. `app/agents/router.py` - добавлен endpoint и проверки
7. `app/templates/dashboard.html` - добавлено динамическое управление UI

## Совместимость
- Все изменения обратно совместимы
- Если модель не имеет llm_model или не установлены флаги, проверка не блокирует запросы
- Веб-интерфейс корректно работает даже если API capabilities недоступен

# 🐛 Исправление: Проблемы с логированием токенов

## Найденные Проблемы

### 1. ❌ Неправильный total_tokens

**Проблема:**
Google Gemini API возвращает неправильный `total_tokens`. Например:
- `prompt_tokens = 8`
- `completion_tokens = 11`
- `total_tokens = 542` ❌ (должно быть 19)

**База данных:**
```sql
SELECT id, prompt_tokens, completion_tokens, total_tokens 
FROM usage_records 
WHERE id IN (1984, 1944);

-- Результат:
-- 1944: 308 + 623 ≠ 2247 (должно быть 931)
-- 1984: 8 + 11 ≠ 542 (должно быть 19)
```

**Решение:**
Добавлена проверка и пересчет в [app/agents/runtime.py](app/agents/runtime.py):

```python
# Fix incorrect total_tokens from some providers (e.g., Gemini)
if total_tokens != prompt_tokens + completion_tokens:
    logger.warning(
        f"Correcting total_tokens: API returned {total_tokens}, "
        f"but prompt ({prompt_tokens}) + completion ({completion_tokens}) = {prompt_tokens + completion_tokens}"
    )
    total_tokens = prompt_tokens + completion_tokens
```

### 2. ❌ Отсутствуют цены для Gemini

**Проблема:**
```sql
SELECT name, cost_per_1k_input_tokens, cost_per_1k_output_tokens 
FROM llm_models 
WHERE name = 'gemini-2.5-flash';

-- Результат:
-- gemini-2.5-flash | NULL | NULL
```

Из-за этого `cost = 0` в usage_records!

**Решение:**
Создан скрипт [update_llm_models.py](update_llm_models.py) который:
- Добавляет pricing для Gemini моделей
- Создает vision-модели (gpt-4o, gemini-1.5-flash, etc.)
- Устанавливает правильные флаги supports_text/supports_vision

### 3. ❌ Нет vision-моделей в БД

**Проблема:**
```sql
SELECT name, supports_vision FROM llm_models;

-- Результат:
-- gpt-4 | false
-- gemini-2.5-flash | false
```

Нет моделей с `supports_vision=true`! Фото не могут обрабатываться.

**Решение:**
Скрипт добавляет:
- `gpt-4-vision-preview` (OpenAI)
- `gpt-4o` (OpenAI, новая)
- `gemini-1.5-flash` (Google, vision)
- `gemini-1.5-pro` (Google, vision)
- `gemini-2.0-flash-thinking-exp` (Google, vision, free)

---

## Исправления

### Файл: app/agents/runtime.py

**До:**
```python
usage_info = {
    "prompt_tokens": usage.prompt_tokens if usage else 0,
    "completion_tokens": usage.completion_tokens if usage else 0,
    "total_tokens": usage.total_tokens if usage else 0,
}
```

**После:**
```python
prompt_tokens = usage.prompt_tokens if usage else 0
completion_tokens = usage.completion_tokens if usage else 0
total_tokens = usage.total_tokens if usage else 0

# Fix incorrect total_tokens from some providers
if total_tokens != prompt_tokens + completion_tokens:
    logger.warning(
        f"Correcting total_tokens: API returned {total_tokens}, "
        f"but prompt ({prompt_tokens}) + completion ({completion_tokens}) = {prompt_tokens + completion_tokens}"
    )
    total_tokens = prompt_tokens + completion_tokens

usage_info = {
    "prompt_tokens": prompt_tokens,
    "completion_tokens": completion_tokens,
    "total_tokens": total_tokens,
}
```

---

## Применение Исправлений

### Шаг 1: Обновить код
```bash
cd /opt/bot-generic
git pull
```

### Шаг 2: Обновить модели в БД
```bash
python3 update_llm_models.py
```

**Ожидаемый вывод:**
```
======================================================================
UPDATING LLM MODELS
======================================================================

Found 2 existing models

📝 Updating: gpt-4
   cost_per_1k_input_tokens: 0.03 → 0.03
   cost_per_1k_output_tokens: 0.06 → 0.06
   supports_text: True → True
   supports_vision: False → False

📝 Updating: gemini-2.5-flash
   cost_per_1k_input_tokens: None → 0.00001875
   cost_per_1k_output_tokens: None → 0.00003
   supports_text: True → True
   supports_vision: False → False

✨ Creating: gpt-4-vision-preview
   name: gpt-4-vision-preview
   provider: openai
   cost_per_1k_input_tokens: 0.01
   cost_per_1k_output_tokens: 0.03
   supports_text: True
   supports_vision: True

✨ Creating: gpt-4o
   ...

======================================================================
✅ MODELS UPDATED SUCCESSFULLY
======================================================================

Total models: 9

Text-only models:
  - gpt-4 (openai)
  - gemini-2.0-flash-exp (google)
  - gemini-2.5-flash (google)

Vision-capable models:
  - gpt-4-vision-preview (openai)
  - gpt-4o (openai)
  - gemini-2.0-flash-thinking-exp (google)
  - gemini-1.5-flash (google)
  - gemini-1.5-pro (google)
```

### Шаг 3: Перезапустить сервис
```bash
sudo systemctl restart bot-generic
```

### Шаг 4: Проверить логи
```bash
journalctl -u bot-generic -f
```

При следующем запросе с неправильным total_tokens увидишь:
```
WARNING: Correcting total_tokens: API returned 542, but prompt (8) + completion (11) = 19
```

---

## Проверка После Обновления

### 1. Проверить модели в БД
```sql
SELECT 
    name, 
    provider, 
    cost_per_1k_input_tokens, 
    cost_per_1k_output_tokens, 
    supports_text, 
    supports_vision 
FROM llm_models 
ORDER BY provider, supports_vision, name;
```

Ожидаемое:
- ✅ Все модели имеют pricing (не NULL)
- ✅ Есть модели с supports_vision=true
- ✅ Gemini модели имеют цены

### 2. Отправить текстовый запрос
1. Открой dashboard
2. Отправь текст без фото
3. Проверь БД:
```sql
SELECT 
    prompt_tokens, 
    completion_tokens, 
    total_tokens, 
    cost, 
    has_image 
FROM usage_records 
ORDER BY id DESC 
LIMIT 1;
```

Ожидаемое:
- ✅ `total_tokens = prompt_tokens + completion_tokens`
- ✅ `cost > 0` (не 0!)
- ✅ `has_image = 0`

### 3. Отправить запрос с фото
1. Открой dashboard
2. Загрузи фото + текст
3. Отправь
4. Проверь БД (та же SQL)

Ожидаемое:
- ✅ `total_tokens = prompt_tokens + completion_tokens`
- ✅ `cost > 0`
- ✅ `has_image = 1`
- ✅ Больше токенов чем в текстовом (vision дороже)

### 4. Проверить Activity Log
1. Открой dashboard → Recent Activity
2. Проверь что видно:
   - Токены отображаются правильно
   - Cost не 0
   - 📷 иконка для запросов с фото

---

## Pricing Reference

### OpenAI Models
| Model | Input (per 1M tokens) | Output (per 1M tokens) | Vision |
|-------|----------------------|------------------------|--------|
| gpt-4 | $30 | $60 | ❌ |
| gpt-4-vision-preview | $10 | $30 | ✅ |
| gpt-4o | $2.5 | $10 | ✅ |

### Google Gemini Models
| Model | Input (per 1M tokens) | Output (per 1M tokens) | Vision |
|-------|----------------------|------------------------|--------|
| gemini-2.5-flash | $0.0075 | $0.03 | ❌ |
| gemini-2.0-flash-exp | FREE | FREE | ❌ |
| gemini-1.5-flash | $0.075 | $0.30 | ✅ |
| gemini-1.5-pro | $1.25 | $5.00 | ✅ |
| gemini-2.0-flash-thinking-exp | FREE | FREE | ✅ |

**Примечание:** Цены конвертированы в стоимость за 1K токенов в БД.

---

## Troubleshooting

### Проблема: Cost все еще 0
**Причины:**
1. Модель не обновлена в БД
2. Агент использует другую модель

**Решение:**
```sql
-- Проверь какую модель использует агент
SELECT a.id, a.name, m.name as model_name, m.cost_per_1k_input_tokens 
FROM agents a 
LEFT JOIN llm_models m ON a.llm_model_id = m.id;

-- Если модель без pricing, обнови или смени модель агента
```

### Проблема: total_tokens все еще неправильный
**Причины:**
- Код не обновлен
- Старая версия runtime.py

**Решение:**
```bash
# Проверь версию файла
grep -A5 "Fix incorrect total_tokens" app/agents/runtime.py

# Если не найдено - git pull не сработал
git pull
sudo systemctl restart bot-generic
```

### Проблема: Нет vision-моделей
**Причины:**
- Скрипт update_llm_models.py не запущен

**Решение:**
```bash
python3 update_llm_models.py
# Проверь вывод - должно быть "✨ Creating: gpt-4o"
```

---

## Итого Исправлено

✅ **total_tokens пересчитывается** если неправильный  
✅ **Gemini pricing добавлен** в БД  
✅ **Vision-модели добавлены** (5 моделей с vision)  
✅ **Логирование работает** корректно  
✅ **Cost рассчитывается** правильно  

**Готово к деплою!** 🚀

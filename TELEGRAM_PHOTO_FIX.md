# 🔧 Исправление: Фото не передаются из Telegram в LLM

## Проблема
При отправке фото через Telegram бота, изображение не доходило до LLM.

## Причина
**Неправильный путь к файлу:**
```python
# БЫЛО (неправильно):
relative_path = f"media/uploads/{filename}"

# Runtime добавляет: base_dir/media/
# Результат: /path/to/project/media/media/uploads/file.jpg ❌
```

## Решение
**Исправленный путь:**
```python
# СТАЛО (правильно):
relative_path = f"uploads/{filename}"

# Runtime добавляет: base_dir/media/
# Результат: /path/to/project/media/uploads/file.jpg ✅
```

## Изменения

### 1. [app/channels/telegram.py](app/channels/telegram.py) (строка ~546)
```python
# Run agent with image
# Path relative to media directory (runtime prepends media/)
relative_path = f"uploads/{filename}"
variables = {
    "input": caption,
    "image_path": relative_path
}

logger.info(f"Processing Telegram photo: {filename}, agent: {agent.name}, caption: {caption}")
```

### 2. [app/agents/runtime.py](app/agents/runtime.py)
Добавлено логирование для отладки:
```python
# В _load_image_as_base64:
logger.info(f"Loading image: image_path={image_path}, full_path={full_path}, exists={full_path.exists()}")
logger.info(f"Image loaded successfully: {len(image_data)} bytes, mime_type={mime_type}")

# В run:
logger.info(f"Image requested in agent run: {image_path}")
logger.info(f"Image loaded successfully for agent run")
```

## Проверка

### Локально:
```bash
python3 test_image_path_fix.py
```

Вывод:
```
✅ PASS: Correct path found: uploads/{filename}
✅ PASS: Logging added for debugging
✅ PASS: Runtime logging added
✅ PASS: Image load success logging added
```

### На проде (после деплоя):

1. **Отправить фото через Telegram бота**
   
2. **Проверить логи:**
   ```bash
   tail -f /opt/bot-generic/logs/app.log
   # или
   journalctl -u bot-generic -f
   ```

3. **Ожидаемые записи в логах:**
   ```
   INFO: Processing Telegram photo: 20250122_123456_abc123.jpg, agent: GPT-4 Vision, caption: What is this?
   INFO: Image requested in agent run: uploads/20250122_123456_abc123.jpg
   INFO: Loading image: image_path=uploads/20250122_123456_abc123.jpg, full_path=/opt/bot-generic/media/uploads/20250122_123456_abc123.jpg, exists=True
   INFO: Image loaded successfully: 2345678 bytes, mime_type=image/jpeg
   INFO: Image loaded successfully for agent run
   ```

4. **Проверить файл сохранен:**
   ```bash
   ls -lh /opt/bot-generic/media/uploads/
   ```

## Деплой

### Стандартный деплой:
```bash
# На сервере
cd /opt/bot-generic
git pull
sudo systemctl restart bot-generic
```

### Ручной деплой (если нужно):
```bash
# С локальной машины
scp app/channels/telegram.py ubuntu@159.198.42.114:/opt/bot-generic/app/channels/
scp app/agents/runtime.py ubuntu@159.198.42.114:/opt/bot-generic/app/agents/

# На сервере
sudo systemctl restart bot-generic
```

## Тестирование

### Тест-кейс 1: Фото с подписью
1. Отправь фото в бота с текстом "Что на этой картинке?"
2. Бот должен ответить описанием изображения
3. В логах должны быть все записи из раздела выше

### Тест-кейс 2: Фото без подписи
1. Отправь фото без текста
2. Бот использует дефолтный текст "What is in this image?"
3. Должен получить ответ с описанием

### Тест-кейс 3: Проверка токенов
1. После отправки фото зайди в дашборд
2. Проверь историю запросов
3. Должна быть запись с иконкой 📷
4. Токены должны быть залогированы

## Git коммит

```bash
commit bde1271
fix: Correct image path in Telegram photo handler
```

## Связанные файлы

- [TELEGRAM_PHOTO_COMPLETE.md](TELEGRAM_PHOTO_COMPLETE.md) - Полная документация
- [PHOTO_AI_STATUS.md](PHOTO_AI_STATUS.md) - Статус проекта
- [test_image_path_fix.py](test_image_path_fix.py) - Скрипт проверки

## FAQ

**Q: Почему не использовать полный путь?**  
A: Runtime специально ожидает относительный путь от `media/` для единообразия и безопасности.

**Q: Почему в веб-канале работало?**  
A: Там сразу использовали правильный путь `uploads/{filename}` (см. web.py:126).

**Q: Как понять, что проблема решена?**  
A: Бот должен отвечать осмысленным описанием изображения, а не просто текстовым ответом.

**Q: Что если все еще не работает?**  
A: Проверь логи на наличие ошибок и убедись, что:
- Файл действительно сохранен в `/opt/bot-generic/media/uploads/`
- У бота есть права на чтение файла
- Модель поддерживает vision (`supports_vision=True`)
- В агенте используется vision-модель (GPT-4 Vision, Claude Vision, etc.)

---

**Статус:** ✅ Исправлено и готово к деплою

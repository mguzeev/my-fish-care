import pytest
from unittest.mock import AsyncMock
from app.core.config import settings
from app.channels.telegram import telegram_channel


@pytest.mark.asyncio
async def test_telegram_webhook_secret_success(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    called = AsyncMock()
    monkeypatch.setattr(telegram_channel, "handle_message", called)

    resp = await client.post(
        settings.telegram_webhook_path,
        headers={"x-telegram-bot-api-secret-token": "secret-token"},
        json={"update_id": 1},
    )

    assert resp.status_code == 200
    called.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_webhook_secret_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    called = AsyncMock()
    monkeypatch.setattr(telegram_channel, "handle_message", called)

    resp = await client.post(
        settings.telegram_webhook_path,
        headers={"x-telegram-bot-api-secret-token": "wrong"},
        json={"update_id": 2},
    )

    assert resp.status_code == 403
    called.assert_not_awaited()

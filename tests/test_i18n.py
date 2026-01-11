from app.i18n.loader import i18n


def test_i18n_basic_en():
    text = i18n.t("start.welcome_existing", "en", name="Alice")
    assert "Alice" in text


def test_i18n_fallback_to_en():
    # non-existent locale should fallback to default
    text = i18n.t("help.text", "de")
    assert "Available Commands" in text or "Доступні команди" in text or "Доступные команды" in text


def test_i18n_missing_key_returns_key():
    text = i18n.t("missing.key", "en")
    assert text == "missing.key"
import pytest
from config.settings import Settings
from utils.errors import ConfigurationError


def test_missing_required_keys_raises():
    with pytest.raises(ConfigurationError):
        Settings(_env_file=None, openrouter_api_key="", postgres_uri="", jwt_secret_key="")


def test_valid_configuration_succeeds():
    settings = Settings(
        _env_file=None, openrouter_api_key="sk-test",
        postgres_uri="postgresql://u:p@localhost:5432/db", jwt_secret_key="test-secret",
    )
    assert settings.redacted_summary()["openrouter_configured"] is True


def test_redacted_summary_has_no_secret_values():
    settings = Settings(
        _env_file=None, openrouter_api_key="sk-super-secret",
        postgres_uri="postgresql://u:p@localhost:5432/db", jwt_secret_key="test-secret",
    )
    assert "sk-super-secret" not in str(settings.redacted_summary())

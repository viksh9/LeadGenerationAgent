import sys

from config.settings import Settings, get_settings
from config.logging import configure_logging


def test_python_version() -> None:
    assert sys.version_info >= (3, 11)


def test_settings_have_expected_defaults() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///:memory:",
        openai_api_key=None,
    )
    assert settings.app_name == "LeadGenerationAgent"
    assert settings.log_level == "INFO"
    assert get_settings().app_name == "LeadGenerationAgent"


def test_configure_logging_does_not_raise() -> None:
    configure_logging("DEBUG")

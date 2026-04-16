"""
tests/test_config.py
---------------------
Verifies that the Settings class parses the DEBUG environment variable
correctly for all known string variants, including non-standard values such
as 'release' and 'prod' that appear in real deployment configs.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.config import Settings
import pytest


def test_debug_parsing_true_values(monkeypatch):
    true_values = ["true", "True", "1", "yes", "on", "t", "y"]
    for val in true_values:
        monkeypatch.setenv("DEBUG", val)
        settings = Settings()
        assert settings.debug is True


def test_debug_parsing_false_values(monkeypatch):
    """Non-standard deployment strings like 'release' must resolve to False."""
    false_values = ["false", "False", "0", "no", "off", "release", "prod", "production", "random_string"]
    for val in false_values:
        monkeypatch.setenv("DEBUG", val)
        settings = Settings()
        assert settings.debug is False


def test_debug_parsing_boolean_true():
    """If instantiated directly with bool True, it should pass through."""
    settings = Settings(debug=True)
    assert settings.debug is True


def test_debug_parsing_boolean_false():
    """If instantiated directly with bool False, it should pass through."""
    settings = Settings(debug=False)
    assert settings.debug is False


# ---------------------------------------------------------------------------
# allowed_origins property
# ---------------------------------------------------------------------------

def test_allowed_origins_debug_mode_no_raw():
    """Debug mode with no raw origins → wildcard ['*']."""
    s = Settings(debug=True, allowed_origins_raw="")
    assert s.allowed_origins == ["*"]


def test_allowed_origins_prod_mode_no_raw():
    """Production mode with no raw origins → empty list (fail-safe)."""
    s = Settings(debug=False, allowed_origins_raw="")
    assert s.allowed_origins == []


def test_allowed_origins_explicit_overrides_debug():
    """Explicit ALLOWED_ORIGINS_RAW always wins, even in debug mode."""
    s = Settings(debug=True, allowed_origins_raw="https://example.com")
    assert s.allowed_origins == ["https://example.com"]


def test_allowed_origins_multiple_origins_parsed():
    """Comma-separated origins are split and whitespace-stripped."""
    s = Settings(debug=False, allowed_origins_raw="  https://a.com , https://b.com  ")
    assert s.allowed_origins == ["https://a.com", "https://b.com"]


def test_docs_enabled_default():
    """docs_enabled defaults to True so developers see /docs locally."""
    s = Settings()
    assert s.docs_enabled is True


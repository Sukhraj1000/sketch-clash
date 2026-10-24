"""Local safeguards load without contacting Google or reading private settings."""
import pytest
from app import config


FIELDS = {
    'GEMINI_PROVIDER_CONCURRENCY': ('gemini_provider_concurrency', 1),
    'GEMINI_REQUESTS_PER_MINUTE': ('gemini_requests_per_minute', 4),
    'GEMINI_REQUESTS_PER_DAY': ('gemini_requests_per_day', 200),
    'GEMINI_MAX_PENDING': ('gemini_max_pending', 8),
}
ISLAND_NAMES = {
    'ISLAND_AI_CONCURRENCY': 'GEMINI_PROVIDER_CONCURRENCY',
    'ISLAND_AI_REQUESTS_PER_MINUTE': 'GEMINI_REQUESTS_PER_MINUTE',
    'ISLAND_AI_REQUESTS_PER_DAY': 'GEMINI_REQUESTS_PER_DAY',
    'ISLAND_AI_MAX_PENDING': 'GEMINI_MAX_PENDING',
}


@pytest.fixture
def isolated_settings(monkeypatch):
    monkeypatch.setattr(config, 'load_dotenv', lambda *args, **kwargs: None)
    for name in [*FIELDS, *ISLAND_NAMES]:
        monkeypatch.delenv(name, raising=False)


def test_conservative_limits_are_enabled_by_default(isolated_settings):
    settings = config.Settings.load()
    for field, expected in FIELDS.values():
        assert getattr(settings, field) == expected


@pytest.mark.parametrize('name,field', [(name, item[0]) for name, item in FIELDS.items()])
def test_limits_are_configurable_but_zero_cannot_disable_them(isolated_settings, monkeypatch, name, field):
    monkeypatch.setenv(name, '3')
    assert getattr(config.Settings.load(), field) == 3
    monkeypatch.setenv(name, '0')
    assert getattr(config.Settings.load(), field) == 1


@pytest.mark.parametrize('name,legacy', ISLAND_NAMES.items())
def test_explicit_island_limits_override_legacy_names(isolated_settings, monkeypatch, name, legacy):
    monkeypatch.setenv(legacy, '7')
    monkeypatch.setenv(name, '3')
    assert getattr(config.Settings.load(), FIELDS[legacy][0]) == 3

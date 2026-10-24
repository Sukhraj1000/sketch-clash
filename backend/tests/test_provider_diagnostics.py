import json
from types import SimpleNamespace

from app import config
from app.config import Settings
from app.provider_diagnostics import configuration_report


def test_inherited_key_wins_and_stale_runtime_value_is_detected(tmp_path, monkeypatch):
    path = tmp_path / '.env.local'
    path.write_text('GEMINI_API_KEY=file-fixture-value\n')
    monkeypatch.setattr(config, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setenv('GEMINI_API_KEY', 'environment-fixture-value')
    settings = Settings.load()
    assert settings.gemini_key_source == 'inherited_environment'
    report = configuration_report(settings, {}, path)
    assert report['loaded_key_matches_current_env_file'] is False
    assert report['loaded_key_matches_process_environment'] is True
    assert 'fixture-value' not in json.dumps(report)


def test_file_key_and_live_client_equality_without_exposing_secrets(tmp_path, monkeypatch):
    path = tmp_path / '.env.local'
    path.write_text('GEMINI_API_KEY=file-fixture-value\n')
    monkeypatch.setattr(config, 'PROJECT_ROOT', tmp_path)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    settings = Settings.load()
    client = SimpleNamespace(_api_client=SimpleNamespace(api_key=settings.gemini_api_key, vertexai=False,
        _http_options=SimpleNamespace(base_url='https://secret-user:secret-pass@generativelanguage.googleapis.com?key=secret-query', api_version='v1beta')))
    report = configuration_report(settings, {'recognition': client}, path)
    assert report['key_source_at_load'] == '.env.local'
    assert report['loaded_key_matches_current_env_file'] is True
    assert report['clients']['recognition']['key_matches_loaded_settings'] is True
    assert report['clients']['recognition']['interactions_endpoint'] == 'https://generativelanguage.googleapis.com/v1beta/interactions'
    assert 'fixture-value' not in json.dumps(report) and 'secret-' not in json.dumps(report)
    path.write_text('GEMINI_API_KEY=new-file-fixture-value\n')
    assert configuration_report(settings, {}, path)['loaded_key_matches_current_env_file'] is False


def test_diagnostics_are_operator_only_and_make_no_provider_request(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from app import provider_diagnostics
    from app.quality_api import OperatorGate
    from app.repository import StoreError
    monkeypatch.setattr(provider_diagnostics, 'PROJECT_ROOT', tmp_path)
    app = FastAPI()
    app.state.operator_gate = OperatorGate(token='operator-fixture-token-long-enough')
    app.state.settings = Settings(gemini_api_key='private-runtime-fixture')
    app.state.recognizer = app.state.colony_planner = app.state.quality_worker = SimpleNamespace(client=None)
    @app.exception_handler(StoreError)
    async def error(request, exc):
        return JSONResponse({'code': exc.code}, status_code=exc.status)
    provider_diagnostics.register_provider_diagnostics(app)
    with TestClient(app) as client:
        assert client.get('/api/quality/provider-diagnostics').status_code == 401
        cookie = app.state.operator_gate.login('operator-fixture-token-long-enough', 'fixture')
        client.cookies.set('sketch_operator', cookie)
        response = client.get('/api/quality/provider-diagnostics')
        assert response.status_code == 200
        assert response.json()['provider_requests_sent'] == 0
        assert 'private-runtime-fixture' not in response.text

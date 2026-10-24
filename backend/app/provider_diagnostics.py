"""Operator-only, no-request checks of the running process's Gemini credentials.

Only equality and provenance leave the process. No key, suffix or digest is
returned, and the check cannot establish a Google project from an opaque key.
"""
from datetime import datetime, timezone
import hmac
import os
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values
from fastapi import Request

from .config import PROJECT_ROOT
from .repository import StoreError


def _same(left, right):
    return hmac.compare_digest(str(left or '').encode(), str(right or '').encode())


def client_check(client, loaded_key):
    if client is None:
        return {'initialized': False}
    internal = getattr(client, '_api_client', None)
    api_key = getattr(internal, 'api_key', None)
    endpoint = None
    # Use the pinned SDK's own Interactions path resolution, without a request.
    try:
        from google.genai._gaos.google_genai import get_google_genai_server_url, get_google_genai_api_version
        raw = get_google_genai_server_url(internal)
        version = get_google_genai_api_version(internal).strip('/')
        url = urlsplit(raw)
        path = '/'.join(part.strip('/') for part in (url.path, version, 'interactions') if part.strip('/'))
        endpoint = urlunsplit((url.scheme, url.hostname or '', '/' + path, '', ''))
    except (AttributeError, TypeError, ValueError):
        pass
    return {'initialized': True, 'key_matches_loaded_settings': _same(api_key, loaded_key) if isinstance(api_key, str) else None,
            'interactions_endpoint': endpoint}


def configuration_report(settings, clients, env_path=None):
    path = env_path or PROJECT_ROOT / '.env.local'
    file_values = dotenv_values(path) if path.exists() else {}
    file_key = file_values.get('GEMINI_API_KEY')
    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None
    return {'pid': os.getpid(), 'settings_loaded_at': settings.settings_loaded_at,
            'key_source_at_load': settings.gemini_key_source,
            'key_configured': bool(settings.gemini_api_key),
            'loaded_key_matches_current_env_file': _same(settings.gemini_api_key, file_key) if file_key is not None else None,
            'loaded_key_matches_process_environment': _same(settings.gemini_api_key, os.getenv('GEMINI_API_KEY')) if 'GEMINI_API_KEY' in os.environ else None,
            'env_file_modified_at': modified,
            'clients': {name: client_check(client, settings.gemini_api_key) for name, client in clients.items()},
            'models': {'recognition': settings.gemini_model, 'council_proposal': settings.colony_proposal_model, 'council_reply': settings.colony_reply_model},
            'project_association': 'Unverified: requires Google project/key metadata; an API key string does not identify its project locally.',
            'provider_requests_sent': 0}


def register_provider_diagnostics(app):
    @app.get('/api/quality/provider-diagnostics')
    async def diagnostics(request: Request):
        if not app.state.operator_gate.check(request.cookies.get('sketch_operator')):
            raise StoreError('Local operator authentication is required.', 401, 'operator_required')
        return configuration_report(app.state.settings, {
            'recognition': getattr(app.state.recognizer, 'client', None),
            'council': getattr(app.state.colony_planner, 'client', None),
            'quality': getattr(app.state.quality_worker, 'agent_client', None),
        })

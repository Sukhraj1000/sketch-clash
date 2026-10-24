"""A single HTTP attempt for each application queue admission.

google-genai 2.33.0 treats HttpRetryOptions.attempts differently in its
Interactions and models transports. Explicitly disable both Interactions retry
configurations; models uses attempts=1, including the original request. Any
later retry must pass through our shared admission queue again.
"""
from google import genai


def create_gemini_client(api_key: str, *, timeout_ms: int = 60000):
    client = genai.Client(api_key=api_key, http_options={
        'timeout': timeout_ms, 'retry_options': {'attempts': 1},
    })
    client.interactions.sdk_configuration.retry_config = None
    client.aio.interactions.sdk_configuration.retry_config = None
    return client

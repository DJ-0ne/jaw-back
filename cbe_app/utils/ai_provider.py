# cbe_app/utils/ai_provider.py
"""
Unified AI provider wrapper.
Supports: Anthropic, OpenAI (and any OpenAI-compatible endpoint), Google Gemini.

Configure in Django settings.py:

    AI_PROVIDER = 'openai'        # 'anthropic' | 'openai' | 'gemini'
    AI_API_KEY  = 'sk-...'        # or set per-provider key below
    AI_MODEL    = 'gpt-4o'        # optional override; sensible defaults used

Per-provider key overrides (optional — AI_API_KEY is the fallback):
    ANTHROPIC_API_KEY = '...'
    OPENAI_API_KEY    = '...'
    GEMINI_API_KEY    = '...'
"""

import os
from django.conf import settings


# ── Default models per provider ──────────────────────────────────────────────
PROVIDER_DEFAULTS = {
    'anthropic': 'claude-sonnet-4-20250514',
    'openai':    'gpt-4o',
    'gemini':    'gemini-1.5-flash',
}


def _get_setting(name: str, fallback: str = '') -> str:
    """Read from Django settings first, then OS env, then fallback."""
    return getattr(settings, name, os.environ.get(name, fallback))


def get_provider() -> str:
    return _get_setting('AI_PROVIDER', 'anthropic').lower().strip()


def get_model(provider: str = None) -> str:
    provider = provider or get_provider()
    return _get_setting('AI_MODEL', PROVIDER_DEFAULTS.get(provider, ''))


def get_api_key(provider: str = None) -> str:
    provider = provider or get_provider()
    # Try provider-specific key first, then generic AI_API_KEY
    key_map = {
        'anthropic': 'ANTHROPIC_API_KEY',
        'openai':    'OPENAI_API_KEY',
        'gemini':    'GEMINI_API_KEY',
    }
    specific_key = _get_setting(key_map.get(provider, ''))
    return specific_key or _get_setting('AI_API_KEY')


# ── Main call ─────────────────────────────────────────────────────────────────

def call_ai(prompt: str, system: str = None, max_tokens: int = 1500) -> str:
    """
    Send a prompt to the configured AI provider and return the text response.

    Args:
        prompt:     The user message / main prompt content.
        system:     Optional system message (ignored by providers that don't support it).
        max_tokens: Maximum tokens in the response.

    Returns:
        str — the model's text response.

    Raises:
        ImportError  — if the required SDK is not installed.
        RuntimeError — if the API call fails.
    """
    provider = get_provider()
    model    = get_model(provider)
    api_key  = get_api_key(provider)

    if not api_key:
        raise RuntimeError(
            f"No API key found for provider '{provider}'. "
            f"Set AI_API_KEY or the provider-specific key in settings/env."
        )

    handlers = {
        'anthropic': _call_anthropic,
        'openai':    _call_openai,
        'gemini':    _call_gemini,
    }

    handler = handlers.get(provider)
    if not handler:
        raise RuntimeError(
            f"Unknown AI provider '{provider}'. "
            f"Supported: {', '.join(handlers.keys())}"
        )

    return handler(prompt=prompt, system=system, model=model, api_key=api_key, max_tokens=max_tokens)


# ── Provider implementations ──────────────────────────────────────────────────

def _call_anthropic(prompt, system, model, api_key, max_tokens):
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs['system'] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text


def _call_openai(prompt, system, model, api_key, max_tokens):
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    client = OpenAI(api_key=api_key)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content


def _call_gemini(prompt, system, model, api_key, max_tokens):
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "google-generativeai package not installed. "
            "Run: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)

    # Gemini supports a system instruction at model level
    model_kwargs = {}
    if system:
        model_kwargs['system_instruction'] = system

    gemini_model = genai.GenerativeModel(model_name=model, **model_kwargs)

    generation_config = genai.GenerationConfig(max_output_tokens=max_tokens)
    response = gemini_model.generate_content(prompt, generation_config=generation_config)
    return response.text
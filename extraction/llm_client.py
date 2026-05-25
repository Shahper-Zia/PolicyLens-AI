import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"
DEFAULT_PROVIDER = "groq"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GROQ_API_URL = "https://api.groq.com/openai/v1"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def load_dotenv_value(key: str) -> str:
    if not ENV_FILE.exists():
        return ""

    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip().strip('"').strip("'")
        return value
    return ""


def resolve_provider(provider: str | None = None) -> str:
    resolved = provider or os.getenv("LLM_PROVIDER") or load_dotenv_value("LLM_PROVIDER") or DEFAULT_PROVIDER
    return resolved.strip().lower()


def resolve_model(provider: str) -> str:
    if provider == "gemini":
        return (
            os.getenv("GEMINI_MODEL")
            or load_dotenv_value("GEMINI_MODEL")
            or DEFAULT_GEMINI_MODEL
        ).strip()
    return (
        os.getenv("GROQ_MODEL")
        or load_dotenv_value("GROQ_MODEL")
        or os.getenv("LLAMA_MODEL")
        or load_dotenv_value("LLAMA_MODEL")
        or DEFAULT_GROQ_MODEL
    ).strip()


def resolve_api_key(provider: str) -> str:
    if provider == "gemini":
        return (
            os.getenv("GEMINI_API_KEY")
            or load_dotenv_value("GEMINI_API_KEY")
        ).strip()
    return (
        os.getenv("GROQ_API_KEY")
        or load_dotenv_value("GROQ_API_KEY")
        or os.getenv("LLAMA_API_KEY")
        or load_dotenv_value("LLAMA_API_KEY")
    ).strip()


def resolve_api_url(provider: str) -> str:
    if provider == "gemini":
        return (
            os.getenv("GEMINI_API_URL")
            or load_dotenv_value("GEMINI_API_URL")
            or ""
        ).strip()
    return (
        os.getenv("GROQ_API_URL")
        or load_dotenv_value("GROQ_API_URL")
        or os.getenv("LLAMA_API_URL")
        or load_dotenv_value("LLAMA_API_URL")
        or DEFAULT_GROQ_API_URL
    ).strip()


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text[3:]
        if text.startswith("json"):
            text = text[4:]
        text = text.lstrip()
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def call_llm_text(
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    temperature: float = 0.1,
    top_p: float = 0.9,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> str:
    resolved_provider = resolve_provider(provider)
    resolved_model = model or resolve_model(resolved_provider)
    resolved_api_key = api_key or resolve_api_key(resolved_provider)
    resolved_api_url = api_url or resolve_api_url(resolved_provider)

    if not resolved_api_key:
        raise RuntimeError(f"{resolved_provider.upper()} API key is not configured.")

    if resolved_provider == "gemini":
        from google import genai

        client = genai.Client(api_key=resolved_api_key)
        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        response = client.models.generate_content(
            model=resolved_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(**config_kwargs),
        )
        return (response.text or "").strip()

    if resolved_provider in {"groq", "llama"}:
        client = OpenAI(api_key=resolved_api_key, base_url=resolved_api_url)
        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if json_mode:
            request_kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**request_kwargs)
        return (response.choices[0].message.content or "").strip()

    raise RuntimeError(f"Unsupported LLM provider: {resolved_provider}")


def call_llm_json(
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    temperature: float = 0.1,
    top_p: float = 0.9,
    max_tokens: int = 1024,
) -> Any:
    text = call_llm_text(
        prompt,
        provider=provider,
        model=model,
        api_key=api_key,
        api_url=api_url,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        json_mode=True,
    )
    return json.loads(_strip_json_fences(text))

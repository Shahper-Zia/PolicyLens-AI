import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


class GroqClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 90,
    ):
        if load_dotenv:
            load_dotenv()

        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL") or os.getenv("LLAMA_MODEL") or DEFAULT_GROQ_MODEL
        self.timeout_seconds = timeout_seconds
        self.openai_client = None

        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not configured.")

        if OpenAI is not None:
            self.openai_client = OpenAI(api_key=self.api_key, base_url=GROQ_BASE_URL)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        if self.openai_client is not None:
            return self._chat_with_openai_sdk(messages, temperature=temperature)

        return self._chat_with_urllib(messages, temperature=temperature)

    def _chat_with_openai_sdk(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""
        except Exception as chat_error:
            try:
                response = self.openai_client.responses.create(
                    model=self.model,
                    input=messages,
                    temperature=temperature,
                )
                return response.output_text
            except Exception as responses_error:
                raise RuntimeError(
                    "Groq request failed using both Responses API and Chat Completions. "
                    f"Responses error: {responses_error}. Chat error: {chat_error}"
                ) from responses_error

    def _chat_with_urllib(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            GROQ_CHAT_COMPLETIONS_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Groq request failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Groq request failed: {exc.reason}") from exc

        return data["choices"][0]["message"]["content"]

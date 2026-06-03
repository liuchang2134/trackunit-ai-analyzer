import os
from typing import Any

from dotenv import load_dotenv

from app.gemini_client import GeminiError, generate_with_gemini, get_gemini_model
from app.ollama_client import DEFAULT_MODEL, OllamaError, generate_with_ollama, get_ollama_model


load_dotenv(override=True)

SUPPORTED_AI_PROVIDERS = {"ollama_local", "gemini"}
FUTURE_AI_PROVIDERS = {"openai", "claude", "deepseek"}


def get_ai_provider(provider_override: str | None = None) -> str:
    return provider_override or os.getenv("AI_PROVIDER", "ollama_local")


def generate_machine_ai_report(prompt: str, machine_context: Any = None, provider_override: str | None = None) -> dict[str, Any]:
    provider = get_ai_provider(provider_override)

    if provider == "ollama_local":
        model = get_ollama_model()
        try:
            return {
                "provider": "ollama_local",
                "model": model,
                "report_markdown": generate_with_ollama(prompt),
                "error": None,
            }
        except OllamaError as exc:
            return {
                "provider": "ollama_local",
                "model": model,
                "report_markdown": "",
                "error": str(exc),
            }

    if provider == "gemini":
        model = get_gemini_model()
        try:
            return {
                "provider": "gemini",
                "model": model,
                "report_markdown": generate_with_gemini(prompt),
                "error": None,
            }
        except GeminiError as exc:
            return {
                "provider": "gemini",
                "model": model,
                "report_markdown": "",
                "error": str(exc),
            }

    return _unsupported_provider_result(provider)


def generate_fleet_ai_report(prompt: str, fleet_context: Any = None, provider_override: str | None = None) -> dict[str, Any]:
    provider = get_ai_provider(provider_override)

    if provider == "ollama_local":
        model = get_ollama_model()
        try:
            return {
                "provider": "ollama_local",
                "model": model,
                "report_markdown": generate_with_ollama(prompt),
                "error": None,
            }
        except OllamaError as exc:
            return {
                "provider": "ollama_local",
                "model": model,
                "report_markdown": "",
                "error": str(exc),
            }

    if provider == "gemini":
        model = get_gemini_model()
        try:
            return {
                "provider": "gemini",
                "model": model,
                "report_markdown": generate_with_gemini(prompt),
                "error": None,
            }
        except GeminiError as exc:
            return {
                "provider": "gemini",
                "model": model,
                "report_markdown": "",
                "error": str(exc),
            }

    return _unsupported_provider_result(provider)


def generate_machine_report(prompt: str, machine_context: Any = None, provider_override: str | None = None) -> dict[str, Any]:
    return generate_machine_ai_report(prompt, machine_context, provider_override)


def generate_fleet_report(prompt: str, fleet_context: Any = None, provider_override: str | None = None) -> dict[str, Any]:
    return generate_fleet_ai_report(prompt, fleet_context, provider_override)


def _unsupported_provider_result(provider: str) -> dict[str, Any]:
    future_note = ""
    if provider in FUTURE_AI_PROVIDERS:
        future_note = f" Provider '{provider}' is reserved for future integration but is not implemented yet."
    return {
        "provider": provider,
        "model": DEFAULT_MODEL,
        "report_markdown": "",
        "error": (
            f"Unsupported AI_PROVIDER: {provider}. Supported values are: "
            f"{', '.join(sorted(SUPPORTED_AI_PROVIDERS))}.{future_note}"
        ),
    }

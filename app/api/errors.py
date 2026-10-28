"""Safe translations from provider failures to HTTP errors."""
from fastapi import HTTPException
from openai import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError


def provider_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RateLimitError):
        return HTTPException(429, "Groq rate limit reached. Please try again shortly.")
    if isinstance(exc, AuthenticationError):
        return HTTPException(503, "Groq rejected the configured API key. Check GROQ_API_KEY.")
    if isinstance(exc, APIConnectionError):
        return HTTPException(502, "Could not connect to Groq. Check your network and try again.")
    if isinstance(exc, APIStatusError):
        body = exc.body if isinstance(exc.body, dict) else {}
        provider_error = body.get("error", body)
        if isinstance(provider_error, dict) and provider_error.get("code") == "model_terms_required":
            return HTTPException(
                403,
                "Groq requires the organization admin to accept the Orpheus English model terms. "
                "Open https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english, "
                "accept the terms, then retry speech playback.",
            )
        if exc.status_code >= 500:
            return HTTPException(502, "Groq is temporarily unavailable. Please try again.")
    if isinstance(exc, RuntimeError) and "GROQ_API_KEY" in str(exc):
        return HTTPException(503, "GROQ_API_KEY is not configured. Add it to .env and restart the app.")
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    return HTTPException(502, "The provider request failed. Please try again.")

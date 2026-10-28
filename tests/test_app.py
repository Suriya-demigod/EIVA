"""Tests for Ruby AI — mocked API calls, no real credentials needed."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.model_registry import get_model, get_default_model, list_models
from app.services.conversation_service import ConversationService
from app.api.errors import provider_http_error


client = TestClient(app)


# ── Health ───────────────────────────────────────────────────────
class TestHealth:
    def test_health_returns_ok(self):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "models" in data
        assert "provider_configured" in data
        assert isinstance(data["models"], dict)

    def test_health_models_availability(self):
        res = client.get("/api/health")
        models = res.json()["models"]
        assert models["fast_chat"] is True
        assert models["reasoning"] is True
        assert models["speech_to_text"] is True
        assert models["text_to_speech"] is True
        assert models["image_generation"] is False  # Phase 8


# ── Model Registry ──────────────────────────────────────────────
class TestModelRegistry:
    def test_get_default_model(self):
        m = get_default_model()
        assert m.model_id == "openai/gpt-oss-20b"

    def test_get_model_by_key(self):
        m = get_model("reasoning")
        assert m is not None
        assert m.model_id == "openai/gpt-oss-120b"

    def test_get_model_missing(self):
        assert get_model("nonexistent") is None

    def test_list_models(self):
        models = list_models()
        assert len(models) >= 9


# ── Conversation Service ────────────────────────────────────────
class TestConversationService:
    def test_add_and_get(self):
        svc = ConversationService()
        svc.add("s1", "user", "hello")
        svc.add("s1", "assistant", "hi!")
        history = svc.get("s1")
        assert len(history) == 2
        assert history[0]["role"] == "user"

    def test_clear(self):
        svc = ConversationService()
        svc.add("s2", "user", "test")
        svc.clear("s2")
        assert svc.get("s2") == []

    def test_bounded_history(self):
        svc = ConversationService()
        for i in range(30):
            svc.add("s3", "user", f"msg-{i}")
        history = svc.get("s3")
        assert len(history) <= 20

    def test_bounded_session_count(self, monkeypatch):
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, "max_sessions", 2)
        svc = ConversationService()
        svc.add("first", "user", "one")
        svc.add("second", "user", "two")
        svc.add("third", "user", "three")
        assert svc.get("first") == []
        assert svc.get("third")[0]["content"] == "three"


# ── Chat endpoint (mocked) ──────────────────────────────────────
class TestChatEndpoint:
    @patch("app.core.orchestrator.get_chat_agent")
    def test_chat_returns_reply(self, mock_get_agent):
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Hello! I'm Ruby.")
        mock_agent.model_id = "openai/gpt-oss-20b"
        mock_get_agent.return_value = mock_agent

        res = client.post("/api/chat", json={
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        })
        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert data["reply"] == "Hello! I'm Ruby."

    def test_chat_rejects_empty_messages(self):
        res = client.post("/api/chat", json={
            "messages": [],
            "stream": False,
        })
        assert res.status_code == 422

    def test_chat_rejects_bad_role(self):
        res = client.post("/api/chat", json={
            "messages": [{"role": "hacker", "content": "test"}],
            "stream": False,
        })
        assert res.status_code == 422

    def test_chat_requires_final_user_message(self):
        res = client.post("/api/chat", json={
            "messages": [{"role": "assistant", "content": "not a user turn"}],
        })
        assert res.status_code == 422

    def test_chat_reports_selected_reasoning_model(self):
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Careful answer")
        mock_agent.model_id = "openai/gpt-oss-120b"
        with patch("app.core.orchestrator.get_reasoning_agent", return_value=mock_agent):
            res = client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "Analyze in detail this issue"}],
            })
        assert res.status_code == 200
        assert res.json()["model"] == "openai/gpt-oss-120b"

    def test_model_identity_answer_comes_from_configuration(self):
        mock_agent = MagicMock()
        mock_agent.model_id = "openai/gpt-oss-20b"
        mock_agent.run = AsyncMock(return_value="incorrect model claim")
        with patch("app.core.orchestrator.get_chat_agent", return_value=mock_agent):
            res = client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "what model am i talking to"}],
            })
        assert res.status_code == 200
        assert res.json()["reply"] == "I'm Ruby, powered by `openai/gpt-oss-20b` through GroqCloud. I'm not the ChatGPT service."
        mock_agent.run.assert_not_called()

    @patch("app.core.orchestrator.get_chat_agent")
    def test_stream_endpoint_encodes_multiline_chunks_as_sse_json(self, mock_get_agent):
        mock_agent = MagicMock()
        mock_agent.model_id = "openai/gpt-oss-20b"

        async def fake_stream(messages):
            yield "first line\nsecond line"
            yield "!"

        mock_agent.run_stream = fake_stream
        mock_get_agent.return_value = mock_agent

        res = client.post("/api/chat/stream", json={
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        })
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        assert '"text": "first line\\nsecond line"' in res.text
        assert '"type": "done"' in res.text

    def test_rejects_invalid_session_id(self):
        res = client.post("/api/chat", headers={"X-Session-Id": "../bad"}, json={
            "messages": [{"role": "user", "content": "Hi"}],
        })
        assert res.status_code == 400

    def test_missing_api_key_returns_actionable_service_error(self):
        with patch("app.core.orchestrator.get_chat_agent", side_effect=RuntimeError("GROQ_API_KEY is not configured")):
            res = client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "Hi"}],
            })
        assert res.status_code == 503
        assert "GROQ_API_KEY" in res.json()["detail"]


class TestVoiceRoutes:
    def test_voice_transcribe_calls_provider(self):
        provider = MagicMock()
        provider.transcribe = AsyncMock(return_value="hello from voice")
        with patch("app.api.routes_voice.get_groq_provider", return_value=provider):
            res = client.post(
                "/api/voice/transcribe",
                files={"file": ("recording.webm", b"fake audio data", "audio/webm")},
            )
        assert res.status_code == 200
        assert res.json() == {"text": "hello from voice", "model": "whisper-large-v3-turbo"}
        provider.transcribe.assert_awaited_once()

    def test_voice_transcribe_rejects_unsupported_type(self):
        res = client.post(
            "/api/voice/transcribe",
            files={"file": ("recording.exe", b"not audio", "application/octet-stream")},
        )
        assert res.status_code == 415

    def test_voice_speak_returns_wav(self):
        provider = MagicMock()
        provider.speak = AsyncMock(return_value=b"RIFFfake-wav")
        with patch("app.api.routes_voice.get_groq_provider", return_value=provider):
            res = client.post("/api/voice/speak", json={"text": "Hello there."})
        assert res.status_code == 200
        assert res.headers["content-type"] == "audio/wav"
        assert res.content == b"RIFFfake-wav"
        provider.speak.assert_awaited_once_with("Hello there.", voice="troy")

    def test_voice_speak_accepts_selected_voice(self):
        provider = MagicMock()
        provider.speak = AsyncMock(return_value=b"RIFFfake-wav")
        with patch("app.api.routes_voice.get_groq_provider", return_value=provider):
            res = client.post("/api/voice/speak", json={"text": "Hello there.", "voice": "hannah"})
        assert res.status_code == 200
        provider.speak.assert_awaited_once_with("Hello there.", voice="hannah")

    def test_voice_speak_rejects_unsupported_voice(self):
        res = client.post("/api/voice/speak", json={"text": "Hello there.", "voice": "unknown"})
        assert res.status_code == 422

    def test_voice_speak_enforces_model_segment_limit(self):
        res = client.post("/api/voice/speak", json={"text": "x" * 201})
        assert res.status_code == 422

    def test_model_terms_error_explains_how_to_enable_speech(self):
        from openai import APIStatusError
        error = MagicMock(spec=APIStatusError)
        error.status_code = 400
        error.body = {"error": {"code": "model_terms_required"}}
        mapped = provider_http_error(error)
        assert mapped.status_code == 403
        assert "accept the Orpheus English model terms" in mapped.detail
        assert "console.groq.com/playground" in mapped.detail

    def test_vision_unavailable(self):
        res = client.post("/api/vision/analyze")
        assert res.status_code == 200
        assert "error" in res.json()


# ── Frontend serving ─────────────────────────────────────────────
class TestFrontend:
    def test_serves_index_html(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "Ruby AI" in res.text

# Ruby AI

A local personal voice and text assistant built with FastAPI, GroqCloud, and a responsive browser UI. Use the microphone button to record a turn: Ruby transcribes it, streams a chat response, then reads the reply aloud. Choose among six English voices in the sidebar; the preference is saved in the browser. Text replies also have listen, pause, and stop controls. The fast model handles ordinary chat; requests with explicit complex-analysis cues use the reasoning model. Conversation history is held in memory and bounded by message count and session count.

## Windows PowerShell setup

Requires Python 3.11 or 3.12 (the pinned dependency set is verified on Python 3.12).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env  # Set GROQ_API_KEY to your key from https://console.groq.com/keys
python run.py
```

Open <http://127.0.0.1:8000>. The API key stays on the server. `/api/health` reports whether a key is configured; it does not verify account access. Never commit `.env`.

## Tests

```powershell
python -m pytest tests/ -v
```

Tests mock model calls and do not require a Groq key. A live model request requires a valid key and account access.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | App status, configured-key flag, and app-enabled model capabilities |
| `/api/chat` | POST | Non-streaming chat |
| `/api/chat/stream` | POST | SSE stream with JSON `delta`, `done`, and `error` events |
| `/docs` | GET | Swagger API docs |
| `/api/voice/transcribe` | POST | Multipart audio transcription with Whisper Large v3 Turbo; 25 MB upload limit |
| `/api/voice/speak` | POST | WAV speech synthesis with Orpheus English; up to 200 characters per request |
| `/api/vision/analyze` | POST | Reserved; unavailable in Phase 1 |

`X-Session-Id` identifies an in-memory conversation. The browser creates a new ID when starting a new chat. Restarting the server clears conversation history.

## Models and phases

| Capability | Model ID | App status |
|---|---|---|
| Fast chat | `openai/gpt-oss-20b` | Implemented; account access depends on your Groq key |
| Reasoning | `openai/gpt-oss-120b` | Implemented; routed by lightweight keyword heuristics |
| Speech-to-text | `whisper-large-v3-turbo` | Implemented; multilingual transcription |
| Text-to-speech | `canopylabs/orpheus-v1-english` | Implemented; English speech |
| Vision | `qwen/qwen3.8-27b` | Reserved for Phase 5 |
| Safety | `openai/gpt-oss-safeguard-20b` | Reserved for Phase 6 |
| Multilingual / function calling | GPT-OSS models | Reserved for Phase 6 |
| Image generation | External provider | Future Phase 8 integration |

Groq documents the audio models and their limits in its [speech-to-text](https://console.groq.com/docs/speech-to-text) and [Orpheus text-to-speech](https://console.groq.com/docs/text-to-speech/orpheus) docs. Orpheus accepts up to 200 characters per request, so longer replies are split into short speech segments by the UI. The browser must allow microphone access; use `http://127.0.0.1:8000` or `http://localhost:8000` so the browser treats it as a secure local origin. Model access depends on the configured API key, account, limits, and service state.

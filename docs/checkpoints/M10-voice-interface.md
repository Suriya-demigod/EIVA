# M10 — Voice interface

**Status:** [x] Complete

## What this builds

Microphone capture, pause detection, speech-to-text, conversation handoff, text-to-speech, and interruptible audio playback. Wake-word support remains optional and is deferred.

## Files changed in this milestone

- `backend/config.py` — voice enable flag and maximum audio-upload size
- `backend/core/model_router.py` — transcription and speech methods on the existing Groq client with safe usage telemetry
- `backend/api/routes/voice.py` — status, bounded audio transcription, and WAV speech endpoints
- `backend/api/routes/__init__.py` — voice route registration export
- `backend/main.py` — voice API and static voice page registration
- `config/models.yaml` — configurable Whisper model, Orpheus model, and voice
- `frontend/index.html` — voice page and explicit microphone/playback controls
- `frontend/voice.js` — microphone permission, silence detection, chat handoff, speech chunking, and stop/cancel behavior
- `frontend/voice.css` — responsive voice page styling
- `scripts/evaluate_voice.py` — deterministic fake-provider evaluation for route and shared-router behavior
- `tests/test_voice_pipeline.py` — unittest entry point for the M10 evaluation
- `README.md` — setup, data handling, and voice route notes
- `docs/IMPLEMENTATION_PLAN.md` — M10 delivered scope and limitations
- `docs/checkpoints/M10-voice-interface.md` — completion record and evaluation
- `milestone.md` — dashboard progress and next milestone
- `backend/core/model_router.py` — TTS follow-up uses the Groq async binary response's supported `read()` method
- `frontend/voice/voice.js` — explains TTS-only failures and waits for audio playback completion safely
- `frontend/voice/index.html` — refreshes the browser script after the TTS fix
- `scripts/evaluate_voice.py` — guards against regression to the unsupported response method and checks playback/error messaging

## Evaluation

Evaluation completed with local fake Groq responses:

- `python -m compileall -q backend scripts tests` — passed
- `python -m scripts.evaluate_voice` — passed: runtime disable/status, explicit mic UI controls, content-type/empty/size checks, shared-router transcription and WAV speech, and transcript-to-chat flow
- `python -m unittest tests.test_voice_pipeline` — 1 test passed
- `node --check` on `frontend/voice.js` via stdin — passed

## TTS playback regression follow-up

- Root cause: Groq's `AsyncAPIResponse` supports `await response.read()`, not `await response.aread()`. Chat and transcription had already succeeded, but the unsupported method raised `AttributeError` while EIVA was downloading the generated speech audio.
- Fixed the shared Groq router to read the WAV response through its async `read()` method. The voice page now reports a speech-specific failure while preserving the already-rendered text answer, and installs playback listeners before starting audio.
- Live verification: the voice API returned HTTP 200 with `audio/wav`, a `RIFF` header, and 122,950 bytes for a short synthetic sentence. The running API reports voice enabled. The browser mic was not activated as part of this check.
- Regression evaluation now verifies the async response method, frontend playback call, speech-specific error message, and cache-busted voice asset.

The test suite does not request a physical microphone or speaker. Browser/device permission and actual playback still need a manual check on the target computer. No live Groq requests were made.

## Completion checks

- [x] A spoken request can be transcribed, sent through the existing chat route, and converted to a spoken response.
- [x] Users can stop recording or interrupt playback.
- [x] Microphone use is visible and starts only after an explicit user action.

## Runtime notes

- Historical note: the original setup line used `EIVA_VOICE_ENABLED`; the implemented setting is `VOICE_ENABLED=true`. See [the current configuration reference](../CONFIGURATION.md).
- The browser detects a speech pause and caps a recording session at 18 seconds; the API separately enforces audio types and a configurable size limit.
- Groq Whisper processes the uploaded recording and Orpheus generates WAV output. The page splits longer answers into requests of at most 200 characters.
- Audio and transcript contents are not written to SQLite or application logs. Groq receives the audio/transcript needed for voice operation; provider usage charges apply.
- Wake-word detection, local STT/TTS, and a hardware browser smoke test are outside the evaluated first slice.


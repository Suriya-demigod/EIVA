# M03 — Context and conversation management

**Status:** [x] Complete  
**State:** Complete

## What this builds

Conversation state, history boundaries, context assembly, prompt instructions, truncation/summarization, and task-scoped context.

## Files changed in this milestone

- `backend/config.py` — local user scope and context/history limits
- `backend/api/schemas.py` — task-scoped chat requests and context metadata in responses
- `backend/api/errors.py` — specific `context_window_exceeded` response code
- `backend/api/routes/chat.py` — context assembly, scoped locking, bounded history, and streamed-turn persistence
- `backend/core/context_builder.py` — versioned system prompt, approximate token budget, and explicit truncation behavior
- `backend/memory/short_term.py` — bounded in-memory history keyed by user, conversation, and task
- `.env.example` — documented context and short-term memory settings
- `docs/checkpoints/M03-context-and-conversation-management.md` — file log and evaluation
- `docs/IMPLEMENTATION_PLAN.md` — M03 completion state and single-user/in-memory boundaries
- `milestone.md` — project progress

## Evaluation

Evaluation completed:

- Python compilation succeeded.
- Local context checks confirmed prior user/assistant turns are reused and separate user/task scopes return separate histories.
- Live chat API preserved a synthetic marker across turns in the same conversation and task.
- The same conversation with a different `task_id` received a shorter context, confirming task isolation.
- A streamed turn was stored after completion and its marker was available to the next turn.
- With a temporary 512-token input limit, a 16,000-character message returned HTTP 413 `context_window_exceeded`.
- With a temporary two-message history cap, the next response set `context_truncated=true`; its estimate remained within the configured limit.
- Context estimates are conservative character-based approximations; provider usage remains authoritative.

## Completion checks

- [x] Multi-turn context is assembled predictably.
- [x] Context is isolated by configured local user, conversation, and task.
- [x] Long histories are bounded and truncation is surfaced in the response and system prompt.

## Remaining work

At M03 completion, history was process-local and scoped to one configured local user. M08 later added durable SQLite history. Authenticated multi-user identity remains outside the implemented scope; the current deployment uses one configured local user.


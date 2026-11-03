"""Assemble bounded, versioned message context for one chat request."""

from dataclasses import dataclass
from math import ceil


SYSTEM_PROMPT_VERSION = "eiva-chat-v1"
SYSTEM_PROMPT = (
    "You are EIVA, a helpful personal assistant. Use the conversation history when it is relevant. "
    "Be clear about uncertainty and do not claim to remember details that are not present in the supplied context."
)
TRUNCATION_NOTE = (
    "Some older conversation turns were omitted to fit the context limit. Do not claim to know details "
    "from omitted turns; ask the user to repeat them when needed."
)


class ContextWindowExceeded(ValueError):
    """Raised when the system prompt and current message exceed the input budget."""


@dataclass(frozen=True)
class BuiltContext:
    messages: list[dict[str, str]]
    estimated_input_tokens: int
    history_truncated: bool
    system_prompt_version: str


class ContextBuilder:
    def __init__(self, max_input_tokens: int) -> None:
        self._max_input_tokens = max_input_tokens

    @staticmethod
    def estimate_tokens(messages: list[dict[str, str]]) -> int:
        """Conservative rough estimate; provider usage remains the authoritative count."""
        return sum(4 + max(1, ceil(len(message["content"].encode("utf-8")) / 4)) for message in messages)

    def build(
        self,
        history: list[dict[str, str]],
        latest_user_message: str,
        *,
        history_was_truncated: bool = False,
    ) -> BuiltContext:
        current = {"role": "user", "content": latest_user_message}
        base_system = {"role": "system", "content": SYSTEM_PROMPT}
        base_messages = [base_system, current]
        if self.estimate_tokens(base_messages) > self._max_input_tokens:
            raise ContextWindowExceeded("The current message exceeds the configured context input budget")

        pairs = [history[index : index + 2] for index in range(0, len(history), 2)]
        selected_pairs: list[list[dict[str, str]]] = []
        truncated = history_was_truncated

        for pair in reversed(pairs):
            if len(pair) != 2 or pair[0].get("role") != "user" or pair[1].get("role") != "assistant":
                truncated = True
                continue
            candidate_pairs = [pair, *selected_pairs]
            candidate_history = [item for selected in candidate_pairs for item in selected]
            if self.estimate_tokens([base_system, *candidate_history, current]) > self._max_input_tokens:
                truncated = True
                break
            selected_pairs = candidate_pairs

        selected_history = [item for pair in selected_pairs for item in pair]
        system = dict(base_system)
        messages = [system, *selected_history, current]

        if truncated:
            system["content"] = f"{SYSTEM_PROMPT}\n\nContext note: {TRUNCATION_NOTE}"
            messages[0] = system
            while selected_pairs and self.estimate_tokens(messages) > self._max_input_tokens:
                selected_pairs.pop(0)
                selected_history = [item for pair in selected_pairs for item in pair]
                messages = [system, *selected_history, current]
            if self.estimate_tokens(messages) > self._max_input_tokens:
                raise ContextWindowExceeded("The current message and context note exceed the configured input budget")

        return BuiltContext(
            messages=messages,
            estimated_input_tokens=self.estimate_tokens(messages),
            history_truncated=truncated,
            system_prompt_version=SYSTEM_PROMPT_VERSION,
        )

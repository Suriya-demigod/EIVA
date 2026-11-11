"""Optional A2A 1.0 HTTP+JSON client for explicitly configured peers."""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator


class A2APeer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_url: str = Field(min_length=1, max_length=2_048)
    token_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", min_length=2, max_length=128)

    @field_validator("card_url")
    @classmethod
    def validate_card_url(cls, value: str) -> str:
        if not _allowed_url(value):
            raise ValueError("A2A peer cards must use HTTPS (HTTP is allowed only for loopback tests)")
        return value


class A2AError(RuntimeError):
    pass


def _allowed_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and (
            parsed.scheme == "https" or (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            )
        )
    except ValueError:
        return False


class A2AClient:
    def __init__(
        self,
        peers: dict[str, A2APeer],
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._peers = peers
        self._timeout = httpx.Timeout(timeout_seconds, connect=3.0)
        self._transport = transport

    @classmethod
    def from_yaml(cls, path: Path, *, timeout_seconds: float = 10.0) -> "A2AClient":
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw_peers = config.get("peers", {})
        if not isinstance(raw_peers, dict):
            raise ValueError("A2A peers configuration must be a mapping")
        peers: dict[str, A2APeer] = {}
        for name, item in raw_peers.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", name):
                raise ValueError("A2A peer names must be lowercase agent identifiers")
            peer = A2APeer.model_validate(item)
            if not _allowed_url(peer.card_url):
                raise ValueError(f"A2A peer '{name}' must use HTTPS (HTTP is allowed only for loopback tests)")
            peers[name] = peer
        return cls(peers, timeout_seconds=timeout_seconds)

    def peer_names(self) -> list[str]:
        return sorted(self._peers)

    @staticmethod
    def _peer_token(env_name: str) -> str | None:
        token = os.environ.get(env_name)
        if token:
            return token
        # pydantic-settings reads .env without exporting it to os.environ.
        # Resolve only the configured token name and never expose the file contents.
        return dotenv_values(Path(".env")).get(env_name)

    async def send_message(self, peer_name: str, message: str, message_id: str) -> dict:
        peer = self._peers.get(peer_name)
        if peer is None:
            raise A2AError("A2A peer is not configured")
        token = self._peer_token(peer.token_env)
        if not token:
            raise A2AError("A2A peer credentials are not configured")

        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False, transport=self._transport) as client:
                card_response = await client.get(peer.card_url, headers={"Accept": "application/json"})
                card_response.raise_for_status()
                if len(card_response.content) > 256_000:
                    raise A2AError("A2A Agent Card exceeded the size limit")
                card = card_response.json()
                if card.get("protocolVersion") not in (None, "1.0"):
                    raise A2AError("A2A peer uses an unsupported protocol version")
                endpoint = next(
                    (
                        item.get("url")
                        for item in card.get("supportedInterfaces", [])
                        if item.get("protocolBinding") == "HTTP+JSON" and item.get("protocolVersion") == "1.0"
                    ),
                    None,
                )
                if not endpoint or not _allowed_url(endpoint):
                    raise A2AError("A2A peer has no supported HTTPS HTTP+JSON interface")
                schemes = card.get("securitySchemes", {})
                has_bearer = any(
                    value.get("httpAuthSecurityScheme", {}).get("scheme", "").lower() == "bearer"
                    for value in schemes.values()
                    if isinstance(value, dict)
                )
                if not has_bearer:
                    raise A2AError("A2A peer does not declare bearer authentication")
                card_origin = urlsplit(peer.card_url)
                endpoint_origin = urlsplit(endpoint)
                if (card_origin.scheme, card_origin.hostname, card_origin.port) != (
                    endpoint_origin.scheme, endpoint_origin.hostname, endpoint_origin.port
                ):
                    raise A2AError("A2A interface origin does not match its configured Agent Card")

                response = await client.post(
                    endpoint.rstrip("/") + "/message:send",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "A2A-Version": "1.0",
                        "Content-Type": "application/a2a+json",
                        "Accept": "application/a2a+json",
                    },
                    json={
                        "message": {
                            "messageId": message_id,
                            "role": "ROLE_USER",
                            "parts": [{"text": message}],
                        }
                    },
                )
                response.raise_for_status()
                if len(response.content) > 1_000_000:
                    raise A2AError("A2A response exceeded the size limit")
                payload = response.json()
                if not isinstance(payload, dict) or not ("task" in payload or "message" in payload):
                    raise A2AError("A2A peer returned an invalid response")
                return payload
        except A2AError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise A2AError(f"A2A communication failed ({type(exc).__name__})") from exc

    async def close(self) -> None:
        return None

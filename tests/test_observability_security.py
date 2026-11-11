"""M14 structured telemetry, redaction, cost estimates, and safe errors."""

import json
import logging
from io import StringIO
import unittest
from types import SimpleNamespace
from uuid import uuid4

from backend.api.errors import unexpected_error_handler
from backend.core.model_router import ModelRouter
from backend.evaluations.model_eval import _redact_report
from backend.main import app
from backend.observability.logging import StructuredFormatter, request_id_var


class ObservabilitySecurityTests(unittest.TestCase):
    def test_formatter_emits_json_correlated_and_redacted_records(self) -> None:
        request_id = str(uuid4())
        token = request_id_var.set(request_id)
        try:
            record = logging.LogRecord(
                "eiva.test", logging.INFO, __file__, 1,
                "Authorization: Bearer secret-token and GROQ_API_KEY=gsk_abcdefghijk",
                (), None,
            )
            payload = json.loads(StructuredFormatter().format(record))
        finally:
            request_id_var.reset(token)
        self.assertEqual(payload["request_id"], request_id)
        self.assertNotIn("secret-token", payload["message"])
        self.assertNotIn("gsk_abcdefghijk", payload["message"])
        self.assertEqual(payload["level"], "INFO")

    def test_configured_cost_is_estimated_and_unconfigured_cost_is_unknown(self) -> None:
        router = ModelRouter(
            SimpleNamespace(), {"chat": "model-a"},
            pricing={"model-a": {"input_usd_per_million_tokens": 1.0, "output_usd_per_million_tokens": 2.0}},
        )
        self.assertEqual(router.estimate_cost("model-a", 1_000_000, 500_000), 2.0)
        self.assertIsNone(router.estimate_cost("model-b", 1, 1))
        self.assertIsNone(router.estimate_cost("model-a", None, 1))

    def test_evaluation_artifact_redacts_credentials_recursively(self) -> None:
        report = _redact_report({"cases": [{"prompt": "Authorization: Bearer secret-token"}], "key": "gsk_abcdefghijk"})
        serialized = json.dumps(report)
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("gsk_abcdefghijk", serialized)
        self.assertIn("[REDACTED]", serialized)


class UnexpectedErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_error_response_does_not_expose_exception_text(self) -> None:
        from starlette.requests import Request

        request_id = uuid4()
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
        request = Request(scope)
        request.state.request_id = request_id
        response = await unexpected_error_handler(request, RuntimeError("secret-token from provider"))
        self.assertEqual(response.status_code, 500)
        body = json.loads(response.body)
        self.assertEqual(body["error"]["request_id"], str(request_id))
        self.assertNotIn("secret-token", response.body.decode())

    async def test_real_request_error_log_has_matching_request_id(self) -> None:
        from fastapi.testclient import TestClient

        async def fail():
            raise RuntimeError("must not be logged")

        route_name = "m14-observability-error-probe"
        app.add_api_route("/_m14-error-probe", fail, methods=["GET"], name=route_name)
        probe_route = next(route for route in app.router.routes if getattr(route, "name", None) == route_name)
        app.router.routes.remove(probe_route)
        app.router.routes.insert(0, probe_route)
        logger = logging.getLogger("eiva.api.errors")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        try:
            response = TestClient(app, raise_server_exceptions=False).get("/_m14-error-probe")
        finally:
            logger.removeHandler(handler)
            app.router.routes[:] = [route for route in app.router.routes if getattr(route, "name", None) != route_name]
        log_record = json.loads(stream.getvalue().strip())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(log_record["request_id"], response.headers["x-request-id"])
        self.assertNotIn("must not be logged", stream.getvalue())


if __name__ == "__main__":
    unittest.main()

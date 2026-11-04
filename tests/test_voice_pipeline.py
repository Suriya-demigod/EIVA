"""Unittest entry point for M10 voice routes and shared router checks."""

import unittest

from scripts.evaluate_voice import main as evaluate_voice


class VoicePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_pipeline(self) -> None:
        await evaluate_voice()


if __name__ == "__main__":
    unittest.main()

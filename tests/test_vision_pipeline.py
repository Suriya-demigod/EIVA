"""Unittest entry point for M11 vision and browser-control evaluations."""

import unittest

from scripts.evaluate_vision import main as evaluate_vision


class VisionPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_vision_and_browser_control(self) -> None:
        await evaluate_vision()


if __name__ == "__main__":
    unittest.main()

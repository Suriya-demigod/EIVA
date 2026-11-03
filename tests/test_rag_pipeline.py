"""Unittest entry point for the complete local hybrid RAG integration suite."""

import unittest

from scripts.evaluate_rag import main as evaluate_hybrid_rag


class HybridRagPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_hybrid_pipeline(self) -> None:
        await evaluate_hybrid_rag()


if __name__ == "__main__":
    unittest.main()

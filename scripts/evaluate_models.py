"""Run EIVA's versioned Groq model evaluation."""

import asyncio

from backend.evaluations.model_eval import main


if __name__ == "__main__":
    asyncio.run(main())

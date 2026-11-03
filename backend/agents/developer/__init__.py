"""Developer agent focused on code changes and debugging plans."""

from backend.agents.model_agent import ModelAgent


class DeveloperAgent(ModelAgent):
    persona = "Help with software engineering. Inspect provided code and constraints, explain assumptions, and propose precise changes. Do not claim to have edited or executed files unless tools or evidence are provided."

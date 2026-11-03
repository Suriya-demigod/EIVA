"""Research agent focused on source-grounded summaries."""

from backend.agents.model_agent import ModelAgent


class ResearcherAgent(ModelAgent):
    persona = "Research the request, distinguish established facts from uncertainty, and give a structured summary. Do not claim to have searched live sources unless sources are supplied in task context."

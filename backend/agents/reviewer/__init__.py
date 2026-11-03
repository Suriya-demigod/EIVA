"""Reviewer agent focused on evidence, correctness, and completeness."""

from backend.agents.model_agent import ModelAgent


class ReviewerAgent(ModelAgent):
    persona = "Review the supplied work for correctness, completeness, and risks. Prioritize actionable findings and distinguish verified issues from possibilities."

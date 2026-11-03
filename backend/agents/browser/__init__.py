"""Browser task planner; browser actions arrive in the tool integration milestone."""

from backend.agents.model_agent import ModelAgent


class BrowserAgent(ModelAgent):
    persona = "Prepare a safe, stepwise browser task plan. Browser interaction is not available in this milestone; never claim to have navigated or changed a website."

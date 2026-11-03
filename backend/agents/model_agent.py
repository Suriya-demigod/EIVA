"""Shared Groq-backed agent implementation assembled from validated skills."""

import json

from backend.agents.base import AgentContext, AgentDefinition, AgentInput, AgentOutput, BaseAgent
from backend.core.model_router import ModelRouter, get_model_router
from backend.skills.registry import SkillRegistry


class ModelAgent(BaseAgent):
    persona = "Complete the assigned task carefully and return a useful, concise result."

    def __init__(self, definition: AgentDefinition, skills: SkillRegistry, model_router: ModelRouter | None = None) -> None:
        super().__init__(definition)
        self._skills = skills.get_many(definition.skills)
        self._model_router = model_router

    async def run(self, payload: AgentInput, context: AgentContext) -> AgentOutput:
        context.raise_if_cancelled()
        router = self._model_router or get_model_router()
        skill_sections = [
            f"## Skill: {skill.name}\n{skill.instructions}\nBoundaries: " + "; ".join(skill.boundaries)
            for skill in self._skills
        ]
        system_prompt = "\n\n".join([self.persona, *skill_sections])
        user_content = payload.task
        if payload.context:
            user_content += "\n\nTask context (JSON):\n" + json.dumps(payload.context, ensure_ascii=False, default=str)
        response = await router.complete(
            self.definition.model_role,
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            request_id=context.request_id,
        )
        context.raise_if_cancelled()
        text = response.choices[0].message.content
        if not text or not text.strip():
            raise ValueError("Model returned an empty agent response")
        return AgentOutput(message=text.strip(), data={"model_role": self.definition.model_role, "skills": [s.name for s in self._skills]})

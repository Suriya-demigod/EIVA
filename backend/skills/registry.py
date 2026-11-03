"""Validated, read-only skill manifest loader."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", min_length=2, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    instructions: str = Field(min_length=1, max_length=12_000)
    boundaries: list[str] = Field(min_length=1, max_length=20)


class UnknownSkillError(LookupError):
    pass


class SkillRegistry:
    def __init__(self, skills: list[SkillDefinition]) -> None:
        self._skills = {skill.name: skill for skill in skills}
        if not skills:
            raise ValueError("No skill manifests were loaded")
        if len(self._skills) != len(skills):
            raise ValueError("Skill manifests contain duplicate names")

    @classmethod
    def from_directory(cls, directory: Path) -> "SkillRegistry":
        if not directory.is_dir():
            raise FileNotFoundError(f"Skill directory does not exist: {directory}")
        skills: list[SkillDefinition] = []
        for path in sorted(directory.glob("*.yaml")):
            config: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
            skill = SkillDefinition.model_validate(config)
            if skill.name != path.stem:
                raise ValueError(f"Skill name in {path.name} must match its filename")
            skills.append(skill)
        return cls(skills)

    def get(self, name: str) -> SkillDefinition:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise UnknownSkillError(f"Skill '{name}' is not configured") from exc

    def get_many(self, names: list[str]) -> list[SkillDefinition]:
        if len(names) != len(set(names)):
            raise ValueError("Agent skill assignments contain duplicates")
        return [self.get(name) for name in names]

    def list(self) -> list[SkillDefinition]:
        return list(self._skills.values())

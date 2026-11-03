"""Config-backed agent discovery contract."""

from fastapi import APIRouter, Depends

from backend.api.schemas import AgentListResponse, AgentSummary
from backend.agents.registry import AgentRegistry, get_agent_registry

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents(
    registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentListResponse:
    return AgentListResponse(
        items=[
            AgentSummary(
                name=definition.name,
                description=definition.description,
                model_role=definition.model_role,
                status="registered" if registered else "planned",
            )
            for definition, registered in registry.definitions()
        ]
    )

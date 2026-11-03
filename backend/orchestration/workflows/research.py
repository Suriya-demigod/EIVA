"""Research task graph: researcher hands evidence to reviewer."""

from backend.orchestration.graph import GraphStep, WorkflowGraph


RESEARCH_GRAPH = WorkflowGraph(
    [
        GraphStep("researcher", "research", 10, 55),
        GraphStep("reviewer", "review research findings", 65, 95),
    ]
)

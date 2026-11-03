"""Coding task graph: developer hands a proposed solution to reviewer."""

from backend.orchestration.graph import GraphStep, WorkflowGraph


CODING_GRAPH = WorkflowGraph(
    [
        GraphStep("developer", "analyze and solve coding task", 10, 55),
        GraphStep("reviewer", "review proposed solution", 65, 95),
    ]
)

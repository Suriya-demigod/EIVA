"""Synchronous invariant checks for M07 task and event structures."""

from uuid import uuid4

from backend.api.schemas import TaskCreateRequest
from backend.orchestration.events import TaskEventBus
from backend.orchestration.supervisor import WORKFLOWS
from backend.tasks.manager import InvalidTaskTransition, TaskManager, TaskRecord, TaskStatus


def expect_rejection(action, expected: type[Exception]) -> None:
    try:
        action()
    except expected:
        return
    raise AssertionError(f"Expected {expected.__name__}")


def main() -> None:
    request = TaskCreateRequest(description="research this", workflow="research", tool_calls=[])
    assert request.workflow == "research"
    expect_rejection(lambda: TaskCreateRequest(description="x", workflow="unknown"), ValueError)

    events = TaskEventBus(history_limit=3, subscriber_queue_size=2)
    manager = TaskManager(events)
    record = TaskRecord(request_id=uuid4(), workflow="coding", description="fix it")
    manager._records[record.id] = record
    manager.transition(record.id, TaskStatus.running)
    manager.update_progress(record.id, 35, "developer step")
    expect_rejection(lambda: manager.update_progress(record.id, 20, "regression"), ValueError)
    manager.set_result(record.id, {"message": "done"})
    manager.transition(record.id, TaskStatus.completed)
    expect_rejection(lambda: manager.transition(record.id, TaskStatus.running), InvalidTaskTransition)
    replay = events.history(record.id)
    assert [event.sequence for event in replay] == [1, 2, 3]
    replay_event = events.publish(record.id, "task.note", {"safe": True})
    replay_after, queue = events.subscribe(record.id, after_sequence=3)
    assert [item.event_id for item in replay_after] == [replay_event.event_id]
    event = events.publish(record.id, "task.note", {"safe": True})
    assert queue.get_nowait().event_id == event.event_id
    events.unsubscribe(record.id, queue)

    assert set(WORKFLOWS) == {"research", "coding"}
    print("task_transitions=passed progress=monotonic event_replay=passed handoff_graphs=2")


if __name__ == "__main__":
    main()

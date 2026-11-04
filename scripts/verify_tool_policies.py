"""Synchronous checks for M06 tool schemas and permission policy."""

from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from backend.core.permission_manager import PermissionDenied, PermissionManager
from backend.tools.gateway import ToolGateway
from backend.tools.schemas import FilesystemReadFile, GitHubReadIssue, PlaywrightNavigate


ROOT = Path(__file__).resolve().parents[1]


def expect_rejection(action, expected: type[Exception]) -> None:
    try:
        action()
    except expected:
        return
    raise AssertionError(f"Expected {expected.__name__}")


def main() -> None:
    gateway = ToolGateway.from_files(
        ROOT / "config/tool_bindings.yaml",
        ROOT / "config/mcp_servers.yaml",
        ROOT / "config/permissions.yaml",
    )
    browser_tools = {
        "playwright.navigate",
        "playwright.snapshot",
        "playwright.click",
        "playwright.take_screenshot",
        "playwright.list_tabs",
        "playwright.select_tab",
        "playwright.create_tab",
        "playwright.close_tab",
        "playwright.type_text",
        "playwright.press_key",
    }
    assert browser_tools <= set(gateway.tool_names())

    permissions = PermissionManager.from_yaml(ROOT / "config/permissions.yaml")
    permissions.authorize("filesystem.read_file", path=str(ROOT / "README.md"))
    expect_rejection(
        lambda: permissions.authorize("filesystem.read_file", path=str(ROOT.parent / "outside.txt")),
        PermissionDenied,
    )
    expect_rejection(lambda: permissions.authorize("filesystem.write_file"), PermissionDenied)
    expect_rejection(lambda: permissions.authorize("unregistered.tool"), PermissionDenied)

    task_id = uuid4()
    expect_rejection(
        lambda: permissions.authorize("filesystem.read_file", path=str(ROOT.parent / "outside.txt"), task_id=task_id),
        PermissionDenied,
    )

    expect_rejection(lambda: FilesystemReadFile.model_validate({"path": "a", "extra": True}), ValidationError)
    expect_rejection(lambda: GitHubReadIssue.model_validate({"owner": "bad owner", "repo": "eiva", "issue_number": 1}), ValidationError)
    expect_rejection(lambda: PlaywrightNavigate.model_validate({"url": "javascript:alert(1)"}), ValidationError)
    assert any(event.reason == "path_outside_allowed_roots" for event in permissions.audit_events())
    assert len(permissions.audit_events(task_id)) == 1
    print(f"tool_bindings={len(gateway.tool_names())} browser_controls=passed read_scope=passed approval_gate=passed schemas=passed task_audit=passed")


if __name__ == "__main__":
    main()

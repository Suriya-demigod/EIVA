"""Strict input models for the tools exposed through EIVA."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilesystemReadFile(ToolArguments):
    path: str = Field(min_length=1, max_length=2048)


class FilesystemListDirectory(ToolArguments):
    path: str = Field(min_length=1, max_length=2048)


class FilesystemWriteFile(ToolArguments):
    path: str = Field(min_length=1, max_length=2048)
    content: str = Field(max_length=1_000_000)


class GitHubGetFile(ToolArguments):
    owner: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    path: str = Field(min_length=1, max_length=2048)
    ref: str | None = Field(default=None, max_length=255)


class GitHubReadIssue(ToolArguments):
    owner: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    issue_number: int = Field(ge=1)
    method: Literal["get", "get_comments", "get_sub_issues", "get_parent", "get_labels"] = "get"
    page: int = Field(default=1, ge=1)
    perPage: int = Field(default=30, ge=1, le=100)


class GitHubCreateIssue(ToolArguments):
    method: Literal["create"] = "create"
    owner: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(default="", max_length=65_536)


class PlaywrightNavigate(ToolArguments):
    url: str = Field(pattern=r"^https?://", max_length=4096)


class PlaywrightSnapshot(ToolArguments):
    pass


class PlaywrightClick(ToolArguments):
    target: str = Field(min_length=1, max_length=2048)

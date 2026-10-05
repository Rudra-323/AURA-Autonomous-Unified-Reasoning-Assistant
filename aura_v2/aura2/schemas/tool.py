from __future__ import annotations

from pydantic import BaseModel


class PendingApproval(BaseModel):
    tool_name: str
    action_label: str
    args: dict
    allowed_decisions: list[str]

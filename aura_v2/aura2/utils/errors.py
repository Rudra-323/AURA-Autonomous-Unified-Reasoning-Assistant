"""
Application exception hierarchy. Low-level libraries raise their own
exceptions; every service/tool boundary catches those and re-raises one of
these instead, with a short, human-safe message. Nothing below this line
should ever reach a client as a raw traceback.
"""

from __future__ import annotations


class AuraError(Exception):
    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class ConfigurationError(AuraError):
    """Missing or invalid configuration at startup."""


class AuthenticationError(AuraError):
    """Missing, invalid, or expired credential/token."""


class AuthorizationError(AuraError):
    """Action attempted without sufficient permission/scope."""


class ToolExecutionError(AuraError):
    """A tool failed to complete its intended action."""


class ExternalServiceError(AuraError):
    """A third-party API failed."""


class DatabaseError(AuraError):
    """A database operation failed."""


class MemoryError_(AuraError):
    """Long-term memory read/write failed. Named to avoid shadowing builtins."""


class ApprovalError(AuraError):
    """Human-in-the-loop approval workflow misused."""


class GuardrailViolation(AuraError):
    """Input or output was blocked by a safety guardrail (prompt injection,
    disallowed content, policy violation). Distinct from ToolExecutionError
    because it's a deliberate block, not a failure."""


class IngestionError(AuraError):
    """Document ingestion (parsing/chunking/embedding) failed."""

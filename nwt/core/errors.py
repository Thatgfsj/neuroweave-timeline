"""Typed exceptions raised by NWT.

Keeping a small, well-named hierarchy makes CLI/MCP error messages actionable
without leaking internals.
"""

from __future__ import annotations


class NWTError(Exception):
    """Base class for all NWT errors."""


class NotInitializedError(NWTError):
    """Raised when an operation requires a .nwt/ workspace that does not exist."""


class AlreadyInitializedError(NWTError):
    """Raised when `nwt init` is run inside an already-initialized workspace."""


class EventNotFoundError(NWTError):
    """Raised when a referenced event id does not exist."""

    def __init__(self, event_id: str) -> None:
        super().__init__(f"event not found: {event_id}")
        self.event_id = event_id


class ValidationError(NWTError):
    """Raised when an event payload fails schema validation."""


class RelationError(NWTError):
    """Raised when a relation cannot be created (unknown type, missing node, etc.)."""

"""Reusable domain-service boundary for HTTP, worker, and CLI entry points.

The legacy handlers hold the established behaviour while P2-1 moves the
public transport surface into domain routers.  Services provide the stable
invocation boundary; subsequent work can move individual handler bodies here
without changing a route or caller.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DomainService:
    """Invoke a domain operation without coupling callers to FastAPI routing."""

    def __init__(self, name: str, handlers: dict[str, Callable[..., Any]]) -> None:
        self.name = name
        self._handlers = handlers

    def invoke(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        try:
            handler = self._handlers[operation]
        except KeyError as exc:
            raise RuntimeError(f"Unknown {self.name} operation: {operation}") from exc
        return handler(*args, **kwargs)


class ProjectService(DomainService):
    pass


class TaskService(DomainService):
    pass


class WorkflowService(DomainService):
    pass


class RagService(DomainService):
    pass


class LearningService(DomainService):
    pass


class SkillService(DomainService):
    pass


class MarketplaceService(DomainService):
    pass


class McpService(DomainService):
    pass


class BenchmarkService(DomainService):
    pass


class LlmService(DomainService):
    pass


class SecurityService(DomainService):
    pass

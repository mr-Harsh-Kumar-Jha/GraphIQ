"""GraphIQ — Event Bus: in-process pub/sub for lifecycle events."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger()


class EventBus:
    """Simple in-process async pub/sub bus.

    Subscribers are async callables. All observers are fire-and-forget —
    they NEVER crash the pipeline even if they throw.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Coroutine[Any, Any, None]]]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """Register a callback for an event type.

        Args:
            event_type: Event name string (e.g. "query_executed").
            callback: Async callable receiving (event_type, payload).
        """
        self._listeners[event_type].append(callback)

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Fire all listeners for an event type.

        Args:
            event_type: Event name string.
            payload: Event data dict.
        """
        for cb in self._listeners.get(event_type, []):
            try:
                await cb(event_type, payload)
            except Exception as e:
                logger.error("observer_error", event_type=event_type, error=str(e))

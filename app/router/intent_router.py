"""GraphIQ — Intent Router: dict-based dispatch from intent_type to handler."""
from __future__ import annotations

from typing import Any

from app.handlers.base import BaseHandler, HandlerResult
from app.core.exceptions import O2CBaseError


class IntentRouter:
    """Routes validated intents to their concrete handler.

    Uses a simple dict lookup — the discriminator field makes
    routing unambiguous. NOT Chain of Responsibility.
    """

    def __init__(self, handler_registry: dict[str, BaseHandler]) -> None:
        self._registry = handler_registry

    async def dispatch(self, intent: Any, context: Any) -> HandlerResult:
        """Dispatch an intent to its registered handler.

        Args:
            intent: A validated intent object with an intent_type attribute.
            context: RequestContext for event emission.

        Returns:
            HandlerResult from the matched handler.

        Raises:
            O2CBaseError: If no handler is registered for the intent type.
        """
        intent_type = getattr(intent, "intent_type", None)
        handler = self._registry.get(str(intent_type))
        if handler is None:
            raise O2CBaseError(
                f"No handler registered for intent type: '{intent_type}'",
                detail=f"Registered types: {', '.join(self._registry.keys())}",
            )
        return await handler.handle(intent, context)

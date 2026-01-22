"""User memory/context storage service."""

import logging
from datetime import datetime
from typing import Protocol

from cachetools import TTLCache

from app.config import get_settings
from app.models.ai_schemas import ConversationTurn, UserContext

logger = logging.getLogger(__name__)

# Maximum conversation history to keep per user
MAX_CONVERSATION_HISTORY = 10


class MemoryStore(Protocol):
    """Protocol for memory storage providers."""

    def get_context(self, user_id: str) -> UserContext | None:
        """Get user context by ID."""
        ...

    def save_context(self, context: UserContext) -> None:
        """Save user context."""
        ...

    def update_context(
        self,
        user_id: str,
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        crop: str | None = None,
        message: str | None = None,
        role: str = "user",
    ) -> UserContext:
        """Update user context with new information."""
        ...

    def clear_context(self, user_id: str) -> None:
        """Clear user context."""
        ...

    def get_or_create_context(self, user_id: str) -> UserContext:
        """Get existing context or create new one."""
        ...

    def add_user_message(self, user_id: str, message: str) -> UserContext:
        """Add a user message to conversation history."""
        ...

    def add_assistant_message(self, user_id: str, message: str) -> UserContext:
        """Add an assistant message to conversation history."""
        ...


class InMemoryStore:
    """In-memory user context storage with TTL."""

    def __init__(self) -> None:
        """Initialize in-memory store with TTL cache."""
        settings = get_settings()
        ttl = settings.memory_ttl_seconds
        self._cache: TTLCache = TTLCache(maxsize=1000, ttl=ttl)

    def get_context(self, user_id: str) -> UserContext | None:
        """
        Get user context by ID.

        Args:
            user_id: User's WhatsApp number or ID.

        Returns:
            UserContext if found, None otherwise.
        """
        return self._cache.get(user_id)

    def save_context(self, context: UserContext) -> None:
        """
        Save user context.

        Args:
            context: UserContext to save.
        """
        context.last_interaction = datetime.now()
        self._cache[context.user_id] = context

    def update_context(
        self,
        user_id: str,
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        crop: str | None = None,
        message: str | None = None,
        role: str = "user",
    ) -> UserContext:
        """
        Update user context with new information.

        Args:
            user_id: User's WhatsApp number or ID.
            city: City to update (if provided).
            latitude: Latitude to update (if provided).
            longitude: Longitude to update (if provided).
            crop: Crop preference to update (if provided).
            message: Message to add to conversation history.
            role: Role for the message (user or assistant).

        Returns:
            Updated UserContext.
        """
        context = self.get_context(user_id)

        if context is None:
            context = UserContext(user_id=user_id)

        if city:
            context.last_city = city
        if latitude is not None:
            context.last_latitude = latitude
        if longitude is not None:
            context.last_longitude = longitude
        if crop:
            context.preferred_crop = crop

        if message:
            turn = ConversationTurn(
                role=role,
                content=message,
                timestamp=datetime.now(),
            )
            context.conversation_history.append(turn)

            # Trim history if too long
            if len(context.conversation_history) > MAX_CONVERSATION_HISTORY:
                context.conversation_history = context.conversation_history[
                    -MAX_CONVERSATION_HISTORY:
                ]

        self.save_context(context)
        return context

    def clear_context(self, user_id: str) -> None:
        """
        Clear user context.

        Args:
            user_id: User's WhatsApp number or ID.
        """
        if user_id in self._cache:
            del self._cache[user_id]

    def get_or_create_context(self, user_id: str) -> UserContext:
        """
        Get existing context or create new one.

        Args:
            user_id: User's WhatsApp number or ID.

        Returns:
            UserContext (existing or new).
        """
        context = self.get_context(user_id)
        if context is None:
            context = UserContext(user_id=user_id)
            self.save_context(context)
        return context

    def add_user_message(self, user_id: str, message: str) -> UserContext:
        """
        Add a user message to conversation history.

        Args:
            user_id: User's WhatsApp number or ID.
            message: User's message content.

        Returns:
            Updated UserContext.
        """
        return self.update_context(user_id, message=message, role="user")

    def add_assistant_message(self, user_id: str, message: str) -> UserContext:
        """
        Add an assistant message to conversation history.

        Args:
            user_id: User's WhatsApp number or ID.
            message: Assistant's message content.

        Returns:
            Updated UserContext.
        """
        return self.update_context(user_id, message=message, role="assistant")


class RedisMemoryStore:
    """Redis-backed memory store for production."""

    def __init__(self, redis_url: str, ttl: int = 3600) -> None:
        """
        Initialize Redis memory store.

        Args:
            redis_url: Redis connection URL.
            ttl: Time-to-live for cached contexts in seconds.
        """
        try:
            import redis.asyncio as redis_async
            self._redis = redis_async.from_url(redis_url, decode_responses=True)
            self._sync_redis = None
            self._ttl = ttl
            self._connected = True
            logger.info("Redis memory store initialized")
        except ImportError:
            logger.warning("redis package not installed, Redis store unavailable")
            self._redis = None
            self._connected = False
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._redis = None
            self._connected = False

    def _get_key(self, user_id: str) -> str:
        """Generate Redis key for user context."""
        return f"user_context:{user_id}"

    def get_context(self, user_id: str) -> UserContext | None:
        """
        Get user context by ID (synchronous wrapper).

        Args:
            user_id: User's WhatsApp number or ID.

        Returns:
            UserContext if found, None otherwise.
        """
        if not self._connected:
            return None

        try:
            import redis
            if self._sync_redis is None:
                settings = get_settings()
                self._sync_redis = redis.from_url(
                    settings.redis_url, decode_responses=True
                )

            data = self._sync_redis.get(self._get_key(user_id))
            if data:
                return UserContext.model_validate_json(data)
            return None
        except Exception as e:
            logger.error(f"Redis get_context error: {e}")
            return None

    def save_context(self, context: UserContext) -> None:
        """
        Save user context (synchronous wrapper).

        Args:
            context: UserContext to save.
        """
        if not self._connected:
            return

        try:
            import redis
            if self._sync_redis is None:
                settings = get_settings()
                self._sync_redis = redis.from_url(
                    settings.redis_url, decode_responses=True
                )

            context.last_interaction = datetime.now()
            self._sync_redis.setex(
                self._get_key(context.user_id),
                self._ttl,
                context.model_dump_json(),
            )
        except Exception as e:
            logger.error(f"Redis save_context error: {e}")

    def update_context(
        self,
        user_id: str,
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        crop: str | None = None,
        message: str | None = None,
        role: str = "user",
    ) -> UserContext:
        """
        Update user context with new information.

        Args:
            user_id: User's WhatsApp number or ID.
            city: City to update (if provided).
            latitude: Latitude to update (if provided).
            longitude: Longitude to update (if provided).
            crop: Crop preference to update (if provided).
            message: Message to add to conversation history.
            role: Role for the message (user or assistant).

        Returns:
            Updated UserContext.
        """
        context = self.get_context(user_id)

        if context is None:
            context = UserContext(user_id=user_id)

        if city:
            context.last_city = city
        if latitude is not None:
            context.last_latitude = latitude
        if longitude is not None:
            context.last_longitude = longitude
        if crop:
            context.preferred_crop = crop

        if message:
            turn = ConversationTurn(
                role=role,
                content=message,
                timestamp=datetime.now(),
            )
            context.conversation_history.append(turn)

            # Trim history if too long
            if len(context.conversation_history) > MAX_CONVERSATION_HISTORY:
                context.conversation_history = context.conversation_history[
                    -MAX_CONVERSATION_HISTORY:
                ]

        self.save_context(context)
        return context

    def clear_context(self, user_id: str) -> None:
        """
        Clear user context.

        Args:
            user_id: User's WhatsApp number or ID.
        """
        if not self._connected:
            return

        try:
            import redis
            if self._sync_redis is None:
                settings = get_settings()
                self._sync_redis = redis.from_url(
                    settings.redis_url, decode_responses=True
                )

            self._sync_redis.delete(self._get_key(user_id))
        except Exception as e:
            logger.error(f"Redis clear_context error: {e}")

    def get_or_create_context(self, user_id: str) -> UserContext:
        """
        Get existing context or create new one.

        Args:
            user_id: User's WhatsApp number or ID.

        Returns:
            UserContext (existing or new).
        """
        context = self.get_context(user_id)
        if context is None:
            context = UserContext(user_id=user_id)
            self.save_context(context)
        return context

    def add_user_message(self, user_id: str, message: str) -> UserContext:
        """
        Add a user message to conversation history.

        Args:
            user_id: User's WhatsApp number or ID.
            message: User's message content.

        Returns:
            Updated UserContext.
        """
        return self.update_context(user_id, message=message, role="user")

    def add_assistant_message(self, user_id: str, message: str) -> UserContext:
        """
        Add an assistant message to conversation history.

        Args:
            user_id: User's WhatsApp number or ID.
            message: Assistant's message content.

        Returns:
            Updated UserContext.
        """
        return self.update_context(user_id, message=message, role="assistant")


# Singleton instance
_memory_store: InMemoryStore | RedisMemoryStore | None = None


def get_memory_store() -> InMemoryStore | RedisMemoryStore:
    """Get or create the memory store instance."""
    global _memory_store
    if _memory_store is None:
        settings = get_settings()
        if settings.use_redis and settings.redis_url:
            _memory_store = RedisMemoryStore(
                settings.redis_url, settings.memory_ttl_seconds
            )
            logger.info("Using Redis memory store")
        else:
            _memory_store = InMemoryStore()
            logger.info("Using in-memory store")
    return _memory_store


def clear_memory_store() -> None:
    """Clear and reset the memory store."""
    global _memory_store
    _memory_store = None

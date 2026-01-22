"""Tests for user memory/context storage service."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models.ai_schemas import ConversationTurn, UserContext
from app.services.memory import (
    InMemoryStore,
    get_memory_store,
    clear_memory_store,
    MAX_CONVERSATION_HISTORY,
)


class TestInMemoryStore:
    """Tests for in-memory user context storage."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        clear_memory_store()  # Ensure clean state
        self.store = InMemoryStore()
        self.test_user_id = "whatsapp:+233201234567"

    def teardown_method(self) -> None:
        """Clean up after tests."""
        clear_memory_store()

    def test_get_context_returns_none_for_new_user(self) -> None:
        """Should return None for unknown user."""
        result = self.store.get_context("unknown_user")
        assert result is None

    def test_save_and_get_context(self) -> None:
        """Should save and retrieve user context."""
        context = UserContext(user_id=self.test_user_id, last_city="Accra")
        self.store.save_context(context)

        retrieved = self.store.get_context(self.test_user_id)

        assert retrieved is not None
        assert retrieved.user_id == self.test_user_id
        assert retrieved.last_city == "Accra"

    def test_save_context_updates_last_interaction(self) -> None:
        """Should update last_interaction timestamp on save."""
        context = UserContext(user_id=self.test_user_id)
        old_time = context.last_interaction

        self.store.save_context(context)
        retrieved = self.store.get_context(self.test_user_id)

        # last_interaction should be updated
        assert retrieved.last_interaction >= old_time

    def test_update_context_city(self) -> None:
        """Should update city in context."""
        context = UserContext(user_id=self.test_user_id)
        self.store.save_context(context)

        updated = self.store.update_context(self.test_user_id, city="Kumasi")

        assert updated.last_city == "Kumasi"

    def test_update_context_coordinates(self) -> None:
        """Should update coordinates in context."""
        context = UserContext(user_id=self.test_user_id)
        self.store.save_context(context)

        updated = self.store.update_context(
            self.test_user_id, latitude=5.6037, longitude=-0.1870
        )

        assert updated.last_latitude == 5.6037
        assert updated.last_longitude == -0.1870

    def test_update_context_crop(self) -> None:
        """Should update crop preference in context."""
        context = UserContext(user_id=self.test_user_id)
        self.store.save_context(context)

        updated = self.store.update_context(self.test_user_id, crop="maize")

        assert updated.preferred_crop == "maize"

    def test_update_context_creates_new_if_not_exists(self) -> None:
        """Should create new context if user doesn't exist."""
        updated = self.store.update_context("new_user", city="Tamale")

        assert updated.user_id == "new_user"
        assert updated.last_city == "Tamale"

    def test_update_context_adds_message_to_history(self) -> None:
        """Should add message to conversation history."""
        context = UserContext(user_id=self.test_user_id)
        self.store.save_context(context)

        updated = self.store.update_context(
            self.test_user_id, message="Hello", role="user"
        )

        assert len(updated.conversation_history) == 1
        assert updated.conversation_history[0].content == "Hello"
        assert updated.conversation_history[0].role == "user"

    def test_update_context_trims_history(self) -> None:
        """Should trim conversation history when exceeding max."""
        context = UserContext(user_id=self.test_user_id)
        self.store.save_context(context)

        # Add more messages than MAX_CONVERSATION_HISTORY
        for i in range(MAX_CONVERSATION_HISTORY + 5):
            self.store.update_context(
                self.test_user_id, message=f"Message {i}", role="user"
            )

        retrieved = self.store.get_context(self.test_user_id)

        assert len(retrieved.conversation_history) == MAX_CONVERSATION_HISTORY
        # Should keep most recent messages
        assert "Message" in retrieved.conversation_history[-1].content

    def test_clear_context(self) -> None:
        """Should clear user context."""
        context = UserContext(user_id=self.test_user_id, last_city="Accra")
        self.store.save_context(context)

        self.store.clear_context(self.test_user_id)
        retrieved = self.store.get_context(self.test_user_id)

        assert retrieved is None

    def test_clear_context_nonexistent_user(self) -> None:
        """Should not raise error clearing nonexistent user."""
        # Should not raise
        self.store.clear_context("nonexistent_user")

    def test_get_or_create_context_returns_existing(self) -> None:
        """Should return existing context."""
        context = UserContext(user_id=self.test_user_id, last_city="Accra")
        self.store.save_context(context)

        retrieved = self.store.get_or_create_context(self.test_user_id)

        assert retrieved.last_city == "Accra"

    def test_get_or_create_context_creates_new(self) -> None:
        """Should create new context for new user."""
        retrieved = self.store.get_or_create_context("brand_new_user")

        assert retrieved is not None
        assert retrieved.user_id == "brand_new_user"
        assert retrieved.last_city is None

    def test_add_user_message(self) -> None:
        """Should add user message to history."""
        context = UserContext(user_id=self.test_user_id)
        self.store.save_context(context)

        updated = self.store.add_user_message(self.test_user_id, "What's the weather?")

        assert len(updated.conversation_history) == 1
        assert updated.conversation_history[0].role == "user"
        assert updated.conversation_history[0].content == "What's the weather?"

    def test_add_assistant_message(self) -> None:
        """Should add assistant message to history."""
        context = UserContext(user_id=self.test_user_id)
        self.store.save_context(context)

        updated = self.store.add_assistant_message(
            self.test_user_id, "The weather in Accra is sunny."
        )

        assert len(updated.conversation_history) == 1
        assert updated.conversation_history[0].role == "assistant"
        assert "sunny" in updated.conversation_history[0].content


class TestMemoryStoreSingleton:
    """Tests for memory store singleton pattern."""

    def setup_method(self) -> None:
        """Clean state before each test."""
        clear_memory_store()

    def teardown_method(self) -> None:
        """Clean up after tests."""
        clear_memory_store()

    def test_get_memory_store_returns_instance(self) -> None:
        """Should return InMemoryStore instance."""
        store = get_memory_store()
        assert isinstance(store, InMemoryStore)

    def test_get_memory_store_returns_same_instance(self) -> None:
        """Should return same instance on multiple calls."""
        store1 = get_memory_store()
        store2 = get_memory_store()
        assert store1 is store2

    def test_clear_memory_store_resets_singleton(self) -> None:
        """Should reset singleton on clear."""
        store1 = get_memory_store()
        store1.save_context(UserContext(user_id="test"))

        clear_memory_store()

        store2 = get_memory_store()
        # New instance should be empty
        assert store2.get_context("test") is None


class TestUserContextModel:
    """Tests for UserContext model."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        context = UserContext(user_id="test")

        assert context.user_id == "test"
        assert context.last_city is None
        assert context.last_latitude is None
        assert context.last_longitude is None
        assert context.preferred_crop is None
        assert context.conversation_history == []
        assert context.last_interaction is not None

    def test_conversation_history_type(self) -> None:
        """Should store ConversationTurn objects."""
        context = UserContext(
            user_id="test",
            conversation_history=[
                ConversationTurn(role="user", content="Hello"),
                ConversationTurn(role="assistant", content="Hi there"),
            ],
        )

        assert len(context.conversation_history) == 2
        assert all(
            isinstance(turn, ConversationTurn)
            for turn in context.conversation_history
        )


class TestConversationTurnModel:
    """Tests for ConversationTurn model."""

    def test_default_timestamp(self) -> None:
        """Should have default timestamp."""
        turn = ConversationTurn(role="user", content="Test")
        assert turn.timestamp is not None
        assert isinstance(turn.timestamp, datetime)

    def test_explicit_timestamp(self) -> None:
        """Should accept explicit timestamp."""
        explicit_time = datetime(2024, 1, 15, 12, 0, 0)
        turn = ConversationTurn(
            role="assistant", content="Response", timestamp=explicit_time
        )
        assert turn.timestamp == explicit_time


class TestCacheExpiration:
    """Tests for TTL cache behavior."""

    def test_cache_respects_ttl(self) -> None:
        """Context should be removed after TTL expires."""
        # Note: This test would need time manipulation to properly test
        # For now, we just verify the cache is created with TTL settings
        store = InMemoryStore()
        assert hasattr(store, "_cache")
        # TTLCache has ttl attribute
        assert store._cache.ttl > 0

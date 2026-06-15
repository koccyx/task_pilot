"""
Base repository interface for chat data access.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from .models import Message, MessagesData, UserProfile


class BaseChatRepository(ABC):
    """Abstract base class for chat repository implementations."""

    @abstractmethod
    async def read_chat_messages(
        self, chat_id: int, date: Optional[datetime] = None
    ) -> MessagesData:
        """
        Read messages for a specific chat and date.

        Args:
            chat_id: The chat ID to read messages for
            date: The date to read messages for (if None, reads today's file)

        Returns:
            MessagesData object containing the messages
        """
        pass

    @abstractmethod
    async def save_message(self, message: Message, chat_id: int) -> None:
        """
        Save a message to storage.

        Args:
            message: Message object to save
            chat_id: The chat ID to save the message for
        """
        pass

    async def read_recent_messages(
        self,
        chat_id: int,
        limit: int = 50,
    ) -> MessagesData:
        """
        Read recent messages for a chat within a time window.

        Default implementation reads only today's messages.
        Subclasses can override for multi-day support.

        Args:
            chat_id: The chat ID to read messages for
            limit: Maximum number of messages to return

        Returns:
            MessagesData object with recent messages
        """
        # Default: read today's messages and limit
        messages_data = await self.read_chat_messages(chat_id)
        if messages_data.messages and limit > 0:
            messages_data.messages = messages_data.messages[-limit:]
        return messages_data

    @abstractmethod
    async def get_conversation_chain(
        self,
        chat_id: int,
        message_id: int,
        limit: int = 20,
    ) -> List[Message]:
        """
        Get the conversation chain by following reply_to_message_id links.

        Reconstructs the conversation history by traversing the chain of
        reply_to_message_id references, starting from the given message_id.

        Args:
            chat_id: The chat ID to search in
            message_id: The starting message ID to trace back from
            limit: Maximum number of messages to return in the chain

        Returns:
            List of Message objects in chronological order (oldest first)
        """
        pass

    async def get_user_profile(
        self, chat_id: int, telegram_user_id: int
    ) -> Optional[UserProfile]:
        """
        Get persistent user profile for a specific chat and user.
        """
        return None

    async def upsert_user_profile(self, profile: UserProfile) -> UserProfile:
        """
        Create or update a user profile.
        """
        raise NotImplementedError

    async def list_user_profiles(self, chat_id: int) -> List[UserProfile]:
        """List all known Telegram/Kaiten identity mappings in a chat."""
        return []

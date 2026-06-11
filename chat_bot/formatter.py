"""
Message formatter for chat messages.
"""

import logging
from datetime import datetime
from typing import Dict

# Import Pydantic models
from .models import MessagesData, MessageStatistics

logger = logging.getLogger(__name__)


class MessageFormatter:
    """
    Utility class for formatting chat messages for various purposes.
    """

    @staticmethod
    def format_messages_for_summary(messages_data: MessagesData) -> str:
        """
        Format messages data into a readable string for summarization.

        Args:
            messages_data: MessagesData object containing messages array

        Returns:
            Formatted string of messages
        """
        if not messages_data.messages:
            return "No messages."

        formatted_messages = []
        for msg in messages_data.messages:
            try:
                dt = datetime.fromisoformat(msg.timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                time_str = "??:??"

            if msg.text:
                formatted_messages.append(f"[{time_str}] {msg.sender_name}: {msg.text}")
            else:
                formatted_messages.append(
                    f"[{time_str}] {msg.sender_name}: [message without text]"
                )

        return "\n".join(formatted_messages)

    @staticmethod
    def format_messages_for_display(
        messages_data: MessagesData, max_length: int = 100
    ) -> str:
        """
        Format messages for display purposes with optional text truncation.

        Args:
            messages_data: MessagesData object containing messages array
            max_length: Maximum length for message text (default: 100)

        Returns:
            Formatted string of messages for display
        """
        if not messages_data.messages:
            return "No messages."

        formatted_messages = []
        for i, msg in enumerate(messages_data.messages, 1):
            try:
                dt = datetime.fromisoformat(msg.timestamp.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                time_str = "??:??"

            if msg.text:
                text = msg.text
                if len(text) > max_length:
                    text = text[: max_length - 3] + "..."
                formatted_messages.append(
                    f"{i}. [{time_str}] {msg.sender_name}: {text}"
                )
            else:
                formatted_messages.append(
                    f"{i}. [{time_str}] {msg.sender_name}: [message without text]"
                )

        return "\n".join(formatted_messages)

    @staticmethod
    def get_message_statistics(
        messages_data: MessagesData,
    ) -> MessageStatistics:
        """
        Get statistics about the messages.

        Args:
            messages_data: MessagesData object containing messages array

        Returns:
            MessageStatistics object with message statistics
        """
        if not messages_data.messages:
            return MessageStatistics(
                total_messages=0,
                unique_senders=0,
                senders={},
                time_range=None,
            )

        senders: Dict[str, int] = {}
        timestamps = []

        for msg in messages_data.messages:
            senders[msg.sender_name] = senders.get(msg.sender_name, 0) + 1

            if msg.timestamp:
                try:
                    dt = datetime.fromisoformat(msg.timestamp.replace("Z", "+00:00"))
                    timestamps.append(dt)
                except (ValueError, TypeError):
                    pass

        time_range = None
        if timestamps:
            start_time = min(timestamps)
            end_time = max(timestamps)
            time_range = {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_minutes": int((end_time - start_time).total_seconds() / 60),
            }

        return MessageStatistics(
            total_messages=len(messages_data.messages),
            unique_senders=len(senders),
            senders=senders,
            time_range=time_range,
        )

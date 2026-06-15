"""
PostgreSQL repository for chat history and user identity profiles.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import asyncpg
from asyncpg import Pool, Record

from .models import Message, MessagesData, PostgresConfig, UserProfile
from .repository_base import BaseChatRepository

logger = logging.getLogger(__name__)


class ChatRepository(BaseChatRepository):
    """Repository class for managing chat data in PostgreSQL."""

    def __init__(self, postgres_config: PostgresConfig):
        self.postgres_config = postgres_config
        self._pool: Optional[Pool] = None
        self._schema_ready = False

    async def _get_pool(self) -> Pool:
        """Create the connection pool lazily."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self.postgres_config.database_url,
                min_size=1,
                max_size=10,
            )
        if not self._schema_ready:
            await self._ensure_schema()
        return self._pool

    async def _ensure_schema(self) -> None:
        """Initialize tables and indexes."""
        if self._schema_ready:
            return

        pool = self._pool
        if pool is None:
            raise RuntimeError("PostgreSQL pool is not initialized")

        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    sender_name TEXT NOT NULL,
                    telegram_user_id BIGINT,
                    telegram_username TEXT,
                    text TEXT,
                    reply_to_message_id BIGINT,
                    is_bot_message BOOLEAN NOT NULL DEFAULT FALSE,
                    UNIQUE(chat_id, message_id)
                );

                CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_timestamp
                ON chat_messages (chat_id, timestamp);

                CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_reply
                ON chat_messages (chat_id, reply_to_message_id);

                CREATE TABLE IF NOT EXISTS user_profiles (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    telegram_user_id BIGINT NOT NULL,
                    telegram_username TEXT,
                    telegram_display_name TEXT NOT NULL,
                    introduced_name TEXT NOT NULL,
                    kaiten_user_name TEXT,
                    kaiten_user_id BIGINT,
                    introduced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(chat_id, telegram_user_id)
                );

                ALTER TABLE user_profiles
                ADD COLUMN IF NOT EXISTS kaiten_user_id BIGINT;
                """
            )
        self._schema_ready = True

    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime:
        """Convert ISO timestamp to timezone-aware datetime."""
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _message_from_record(record: Record) -> Message:
        """Convert DB row to Message model."""
        timestamp = record["timestamp"]
        if isinstance(timestamp, datetime):
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = str(timestamp)

        return Message(
            timestamp=timestamp_str,
            message_id=record["message_id"],
            sender_name=record["sender_name"],
            telegram_user_id=record["telegram_user_id"],
            telegram_username=record["telegram_username"],
            text=record["text"],
            reply_to_message_id=record["reply_to_message_id"],
            is_bot_message=record["is_bot_message"],
        )

    @staticmethod
    def _profile_from_record(record: Record) -> UserProfile:
        """Convert DB row to UserProfile model."""
        return UserProfile(
            chat_id=record["chat_id"],
            telegram_user_id=record["telegram_user_id"],
            telegram_username=record["telegram_username"],
            telegram_display_name=record["telegram_display_name"],
            introduced_name=record["introduced_name"],
            kaiten_user_name=record["kaiten_user_name"],
            kaiten_user_id=record["kaiten_user_id"],
            introduced_at=record["introduced_at"],
            updated_at=record["updated_at"],
        )

    async def read_chat_messages(
        self, chat_id: int, date: Optional[datetime] = None
    ) -> MessagesData:
        """Read messages for a chat for a specific UTC day."""
        if date is None:
            target = datetime.now(timezone.utc)
        else:
            target = date if date.tzinfo else date.replace(tzinfo=timezone.utc)

        day_start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_id, timestamp, sender_name, telegram_user_id,
                       telegram_username, text, reply_to_message_id, is_bot_message
                FROM chat_messages
                WHERE chat_id = $1 AND timestamp >= $2 AND timestamp < $3
                ORDER BY timestamp ASC, message_id ASC
                """,
                chat_id,
                day_start,
                day_end,
            )

        return MessagesData(messages=[self._message_from_record(row) for row in rows])

    async def save_message(self, message: Message, chat_id: int) -> None:
        """Save a message to PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_messages (
                    chat_id, message_id, timestamp, sender_name,
                    telegram_user_id, telegram_username, text,
                    reply_to_message_id, is_bot_message
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (chat_id, message_id) DO UPDATE SET
                    timestamp = EXCLUDED.timestamp,
                    sender_name = EXCLUDED.sender_name,
                    telegram_user_id = EXCLUDED.telegram_user_id,
                    telegram_username = EXCLUDED.telegram_username,
                    text = EXCLUDED.text,
                    reply_to_message_id = EXCLUDED.reply_to_message_id,
                    is_bot_message = EXCLUDED.is_bot_message
                """,
                chat_id,
                message.message_id,
                self._parse_timestamp(message.timestamp),
                message.sender_name,
                message.telegram_user_id,
                message.telegram_username,
                message.text,
                message.reply_to_message_id,
                message.is_bot_message,
            )

    async def read_recent_messages(
        self, chat_id: int, limit: int = 50, days: int = 1
    ) -> MessagesData:
        """Read recent messages for a chat within a time window."""
        pool = await self._get_pool()
        since = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_id, timestamp, sender_name, telegram_user_id,
                       telegram_username, text, reply_to_message_id, is_bot_message
                FROM chat_messages
                WHERE chat_id = $1 AND timestamp >= $2
                ORDER BY timestamp DESC, message_id DESC
                LIMIT $3
                """,
                chat_id,
                since,
                max(limit, 1),
            )

        messages = [self._message_from_record(row) for row in reversed(rows)]
        return MessagesData(messages=messages)

    async def get_conversation_chain(
        self, chat_id: int, message_id: int, limit: int = 20
    ) -> List[Message]:
        """Follow the reply chain backwards."""
        env_limit = int(os.getenv("CONVERSATION_HISTORY_LIMIT", str(limit)))
        effective_limit = env_limit if env_limit > 0 else limit

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_id, timestamp, sender_name, telegram_user_id,
                       telegram_username, text, reply_to_message_id, is_bot_message
                FROM chat_messages
                WHERE chat_id = $1
                ORDER BY timestamp ASC, message_id ASC
                """,
                chat_id,
            )

        message_index: Dict[int, Message] = {
            row["message_id"]: self._message_from_record(row) for row in rows
        }

        chain: List[Message] = []
        current_id: Optional[int] = message_id
        while current_id is not None and len(chain) < effective_limit:
            current = message_index.get(current_id)
            if current is None:
                break
            chain.append(current)
            current_id = current.reply_to_message_id

        chain.reverse()
        return chain

    async def get_user_profile(
        self, chat_id: int, telegram_user_id: int
    ) -> Optional[UserProfile]:
        """Get a user profile if the user already introduced themselves."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT chat_id, telegram_user_id, telegram_username,
                       telegram_display_name, introduced_name, kaiten_user_name,
                       kaiten_user_id,
                       introduced_at, updated_at
                FROM user_profiles
                WHERE chat_id = $1 AND telegram_user_id = $2
                """,
                chat_id,
                telegram_user_id,
            )

        return self._profile_from_record(row) if row else None

    async def upsert_user_profile(self, profile: UserProfile) -> UserProfile:
        """Create or update the profile and return the stored version."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_profiles (
                    chat_id, telegram_user_id, telegram_username,
                    telegram_display_name, introduced_name, kaiten_user_name,
                    kaiten_user_id, introduced_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
                ON CONFLICT (chat_id, telegram_user_id) DO UPDATE SET
                    telegram_username = EXCLUDED.telegram_username,
                    telegram_display_name = EXCLUDED.telegram_display_name,
                    introduced_name = EXCLUDED.introduced_name,
                    kaiten_user_name = EXCLUDED.kaiten_user_name,
                    kaiten_user_id = EXCLUDED.kaiten_user_id,
                    updated_at = NOW()
                RETURNING chat_id, telegram_user_id, telegram_username,
                          telegram_display_name, introduced_name, kaiten_user_name,
                          kaiten_user_id,
                          introduced_at, updated_at
                """,
                profile.chat_id,
                profile.telegram_user_id,
                profile.telegram_username,
                profile.telegram_display_name,
                profile.introduced_name,
                profile.kaiten_user_name,
                profile.kaiten_user_id,
            )

        if row is None:
            raise RuntimeError("Failed to upsert user profile")
        return self._profile_from_record(row)

    async def list_user_profiles(self, chat_id: int) -> List[UserProfile]:
        """List all known users so every worker can resolve people consistently."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT chat_id, telegram_user_id, telegram_username,
                       telegram_display_name, introduced_name, kaiten_user_name,
                       kaiten_user_id, introduced_at, updated_at
                FROM user_profiles
                WHERE chat_id = $1
                ORDER BY introduced_name ASC, telegram_user_id ASC
                """,
                chat_id,
            )
        return [self._profile_from_record(row) for row in rows]

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._schema_ready = False

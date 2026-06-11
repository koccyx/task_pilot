"""
Telegram message formatter for converting standard Markdown to Telegram-compatible format.

Uses telegramify-markdown to properly handle Markdown elements that Telegram
doesn't natively support, including tables.
"""

import logging

import telegramify_markdown

try:
    import telegramify_markdown.customize as customize
except ImportError:  # pragma: no cover - depends on installed package version
    customize = None

logger = logging.getLogger(__name__)


class TelegramMarkdownFormatter:
    """
    Formats messages for Telegram by converting standard Markdown to MarkdownV2.

    Telegram's native Markdown parser doesn't support tables and has strict
    escaping requirements. This class uses telegramify-markdown to handle
    the conversion automatically.
    """

    # Configure telegramify-markdown for our use case
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Initialize telegramify-markdown settings once."""
        if cls._initialized:
            return

        if customize is not None:
            # Allow non-strict markdown when the installed package exposes
            # runtime customization flags.
            customize.strict_markdown = False
            customize.cite_expandable = True
        else:
            logger.info(
                "telegramify_markdown.customize is unavailable; using default settings"
            )

        cls._initialized = True

    @classmethod
    def format_for_telegram(cls, text: str) -> str:
        """
        Convert standard Markdown to Telegram MarkdownV2 format.

        Tables are converted to preformatted text blocks that display
        nicely in monospace font.

        Args:
            text: Standard Markdown text.

        Returns:
            Telegram MarkdownV2 compatible text.
        """
        cls._ensure_initialized()

        try:
            # Convert to Telegram-compatible format
            formatted: str = telegramify_markdown.markdownify(text)
            return formatted
        except Exception as e:
            logger.warning(
                "Failed to convert Markdown, returning original: %s", e
            )
            return cls._escape_markdown_v2(text)

    @classmethod
    def _escape_markdown_v2(cls, text: str) -> str:
        """
        Escape special characters for MarkdownV2.

        Fallback method when telegramify-markdown fails.

        Args:
            text: Text to escape.

        Returns:
            Escaped text safe for MarkdownV2.
        """
        # Characters that need escaping in MarkdownV2
        special_chars = r"_*[]()~`>#+-=|{}.!"
        escaped = text
        for char in special_chars:
            escaped = escaped.replace(char, f"\\{char}")
        return escaped

    @classmethod
    def get_parse_mode(cls) -> str:
        """
        Get the appropriate parse mode for Telegram.

        Returns:
            The parse mode string to use with Telegram API.
        """
        return "MarkdownV2"


def format_message(text: str) -> tuple[str, str]:
    """
    Convenience function to format a message for Telegram.

    Args:
        text: Standard Markdown text.

    Returns:
        Tuple of (formatted_text, parse_mode).
    """
    formatted = TelegramMarkdownFormatter.format_for_telegram(text)
    parse_mode = TelegramMarkdownFormatter.get_parse_mode()
    return formatted, parse_mode

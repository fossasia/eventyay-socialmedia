import logging
from typing import Any

import requests

from socialmedia.telegram_utils import normalize_telegram_chat_id

from ..utils import validate_safe_url
from .base import BaseSocialProvider, PublishingError

logger = logging.getLogger(__name__)


class TelegramProvider(BaseSocialProvider):
    """Telegram Bot API integration adapter."""

    def __init__(self, account):
        super().__init__(account)
        self.token = self.credentials.get("bot_token")
        self.chat_id = normalize_telegram_chat_id(self.account.platform_username)
        self.base_url = f"https://api.telegram.org/bot{self.token}/"

    def validate_credentials(self) -> bool:
        if not self.token:
            return False
        try:
            response = requests.get(f"{self.base_url}getMe", timeout=10)
            if response.status_code != 200 or not response.json().get("ok", False):
                return False

            if self.chat_id:
                response = requests.get(
                    f"{self.base_url}getChat",
                    params={"chat_id": self._resolve_chat_id()},
                    timeout=10,
                )
                return response.status_code == 200 and response.json().get("ok", False)

            return True
        except Exception as e:
            logger.error(f"Telegram credentials validation failed: {e}")
            return False

    def send_test_message(self) -> dict[str, Any]:
        if not self.token or not self.chat_id:
            return {"success": False, "message": "Missing bot token or chat ID."}
        try:
            bot_info = self._get_bot_info()

            url = f"{self.base_url}sendMessage"
            payload = {
                "chat_id": self._resolve_chat_id(),
                "text": "✅ Connection successful from Eventyay!",
            }
            response = requests.post(url, data=payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    return {
                        "success": True,
                        "message": (
                            f"Test message sent successfully using bot {bot_info}."
                        ),
                    }

            try:
                err_data = response.json()
                desc = err_data.get("description", response.text)
            except Exception:
                desc = response.text

            return {
                "success": False,
                "message": (
                    f"Telegram API error: {desc} (Using bot: {bot_info}). "
                    f"{self._error_hint(desc)}"
                ),
            }
        except requests.RequestException as e:
            return {"success": False, "message": f"Network error: {e}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _resolve_chat_id(self):
        """Return chat_id as int if numeric, otherwise keep as string.

        (e.g. @channel)
        """
        raw = self.chat_id
        try:
            return int(raw)
        except (ValueError, TypeError):
            return raw

    def _get_bot_info(self) -> str:
        try:
            me_res = requests.get(f"{self.base_url}getMe", timeout=10)
            if me_res.status_code == 200:
                me_data = me_res.json()
                if me_data.get("ok"):
                    result = me_data.get("result", {})
                    username = result.get("username") or "unknown"
                    first_name = result.get("first_name") or "Telegram bot"
                    return f"@{username} ({first_name})"
        except Exception:
            pass
        return "Unknown Bot"

    def _error_hint(self, description: str) -> str:
        desc = description.lower()
        if "chat not found" in desc:
            return (
                "For private groups, use the numeric chat ID, usually starting with "
                "-100. Public @usernames work only for public groups/channels."
            )
        if "not enough rights" in desc or "not enough permission" in desc:
            return "Please confirm the bot is an admin and can send messages."
        if "bot was kicked" in desc or "bot is not a member" in desc:
            return "Please add this exact bot back to the group or channel."
        return "Please check the bot token, target chat ID, and bot permissions."

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        if not self.token or not self.chat_id:
            raise PublishingError("Missing Telegram bot token or chat ID.")

        payload = {
            "chat_id": self._resolve_chat_id(),
        }

        try:
            if media and len(media) > 0:
                media_item = media[0]
                is_url = media_item.startswith(("http://", "https://"))

                if is_url:
                    validate_safe_url(media_item)
                    url = f"{self.base_url}sendPhoto"
                    payload.update(
                        {
                            "photo": media_item,
                            "caption": text,
                            "parse_mode": "Markdown",
                        }
                    )
                    response = requests.post(url, data=payload, timeout=15)
                else:
                    url = f"{self.base_url}sendPhoto"
                    payload.update(
                        {
                            "caption": text,
                            "parse_mode": "Markdown",
                        }
                    )
                    with open(media_item, "rb") as f:
                        files = {"photo": f}
                        response = requests.post(
                            url, data=payload, files=files, timeout=20
                        )
            else:
                url = f"{self.base_url}sendMessage"
                payload.update(
                    {
                        "text": text,
                        "parse_mode": "Markdown",
                    }
                )
                response = requests.post(url, data=payload, timeout=15)

            if response.status_code != 200:
                raise PublishingError(f"Telegram API error: {response.text}")

            result = response.json()
            if not result.get("ok"):
                raise PublishingError(f"Telegram API response error: {result}")

            message = result.get("result", {})
            post_id = str(message.get("message_id"))
            if self.chat_id.startswith("@"):
                username = self.chat_id.lstrip("@")
                url_val = f"https://t.me/{username}/{post_id}"
            else:
                clean_id = self.chat_id
                if clean_id.startswith("-100"):
                    clean_id = clean_id[4:]
                elif clean_id.startswith("-"):
                    clean_id = clean_id[1:]
                url_val = f"https://t.me/c/{clean_id}/{post_id}"

            return {
                "post_id": post_id,
                "url": url_val,
            }

        except requests.RequestException as e:
            raise PublishingError(
                f"Network error communicating with Telegram Bot API: {e}"
            ) from e
        except Exception as e:
            raise PublishingError(f"Error publishing to Telegram: {e}") from e

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        return [
            "Message @BotFather on Telegram and send /newbot to create your bot.",
            "Copy the Bot API Token provided by BotFather.",
            "Add the bot as an administrator (or member) to your target group/channel.",
            (
                "Obtain the numeric Channel/Chat ID (prefixed with -100 for "
                "supergroups, e.g. -1004301847700) or public @username, then "
                "input it above."
            ),
        ]

import logging
from typing import Any

import requests

from .base import BaseSocialProvider, PublishingError

logger = logging.getLogger(__name__)


class TelegramProvider(BaseSocialProvider):
    """Telegram Bot API integration adapter."""

    def __init__(self, account):
        super().__init__(account)
        self.token = self.credentials.get("bot_token")
        self.chat_id = self.account.platform_username
        self.base_url = f"https://api.telegram.org/bot{self.token}/"

    def validate_credentials(self) -> bool:
        if not self.token:
            return False
        try:
            response = requests.get(f"{self.base_url}getMe", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("ok", False)
            return False
        except Exception as e:
            logger.error(f"Telegram credentials validation failed: {e}")
            return False

    def send_test_message(self) -> dict[str, Any]:
        if not self.token or not self.chat_id:
            return {"success": False, "message": "Missing bot token or chat ID."}
        try:
            url = f"{self.base_url}sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": "✅ Connection successful from Eventyay!",
                "parse_mode": "Markdown",
            }
            response = requests.post(url, data=payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    return {
                        "success": True,
                        "message": "Test message sent successfully.",
                    }
            return {"success": False, "message": f"Telegram API error: {response.text}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Network error: {e}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        if not self.token or not self.chat_id:
            raise PublishingError("Missing Telegram bot token or chat ID.")

        payload = {
            "chat_id": self.chat_id,
        }

        try:
            if media and len(media) > 0:
                media_item = media[0]
                is_url = media_item.startswith(("http://", "https://"))

                if is_url:
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
                url_val = f"https://t.me/c/{self.chat_id}/{post_id}"

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

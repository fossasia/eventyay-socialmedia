import logging
import requests
from typing import Any, Dict, List, Optional
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

    def publish_post(self, text: str, media: Optional[List[str]] = None) -> Dict[str, Any]:
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
                    payload.update({
                        "photo": media_item,
                        "caption": text,
                        "parse_mode": "Markdown",
                    })
                    response = requests.post(url, data=payload, timeout=15)
                else:
                    url = f"{self.base_url}sendPhoto"
                    payload.update({
                        "caption": text,
                        "parse_mode": "Markdown",
                    })
                    with open(media_item, "rb") as f:
                        files = {"photo": f}
                        response = requests.post(url, data=payload, files=files, timeout=20)
            else:
                url = f"{self.base_url}sendMessage"
                payload.update({
                    "text": text,
                    "parse_mode": "Markdown",
                })
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
            raise PublishingError(f"Network error communicating with Telegram Bot API: {e}")
        except Exception as e:
            raise PublishingError(f"Error publishing to Telegram: {e}")

import logging
from typing import Any

import requests

from .base import BaseSocialProvider, PublishingError

logger = logging.getLogger(__name__)


class BufferProvider(BaseSocialProvider):
    """Buffer API integration adapter."""

    def __init__(self, account):
        super().__init__(account)
        self.access_token = self.credentials.get("access_token")
        self.profile_id = self.account.platform_username
        self.base_url = "https://api.bufferapp.com/1/"

    def validate_credentials(self) -> bool:
        if not self.access_token:
            return False
        try:
            url = f"{self.base_url}user.json"
            response = requests.get(
                url, params={"access_token": self.access_token}, timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Buffer credentials validation failed: {e}")
            return False

    def send_test_message(self) -> dict[str, Any]:
        if not self.access_token:
            return {"success": False, "message": "Missing access token."}
        try:
            url = f"{self.base_url}user.json"
            response = requests.get(
                url, params={"access_token": self.access_token}, timeout=10
            )
            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "Connection successful. Buffer account accessible.",
                }
            return {"success": False, "message": f"Buffer API error: {response.text}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Network error: {e}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        if not self.access_token or not self.profile_id:
            raise PublishingError("Missing Buffer access token or profile ID.")

        url = f"{self.base_url}updates/create.json"
        payload = {
            "text": text,
            "profile_ids[]": [self.profile_id],
        }

        if media and len(media) > 0:
            media_item = media[0]
            if media_item.startswith(("http://", "https://")):
                payload["media[picture]"] = media_item
                payload["media[thumbnail]"] = media_item

        try:
            response = requests.post(
                url,
                data=payload,
                params={"access_token": self.access_token},
                timeout=15,
            )
            if response.status_code != 200:
                raise PublishingError(f"Buffer API error: {response.text}")

            result = response.json()
            updates = result.get("updates", [])
            if not updates:
                raise PublishingError(
                    f"Buffer API response did not contain updates: {result}"
                )

            update = updates[0]
            post_id = str(update.get("id"))
            public_url = f"https://publish.buffer.com/profile/{self.profile_id}/queue"

            return {
                "post_id": post_id,
                "url": public_url,
            }
        except requests.RequestException as e:
            raise PublishingError(
                f"Network error communicating with Buffer API: {e}"
            ) from e
        except Exception as e:
            raise PublishingError(f"Error publishing to Buffer: {e}") from e

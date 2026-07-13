import logging
from typing import Any

import requests

from .base import BaseSocialProvider, PublishingError

logger = logging.getLogger(__name__)


class PostizProvider(BaseSocialProvider):
    """Postiz API integration adapter."""

    def __init__(self, account):
        super().__init__(account)
        self.api_url = self.credentials.get("api_url")
        self.api_key = self.credentials.get("api_key")

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def validate_credentials(self) -> bool:
        if not self.api_url or not self.api_key:
            return False
        try:
            url = f"{self.api_url.rstrip('/')}/v1/workspaces"
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Postiz credentials validation failed: {e}")
            return False

    def send_test_message(self) -> dict[str, Any]:
        if not self.api_url or not self.api_key:
            return {"success": False, "message": "Missing API URL or API key."}
        try:
            url = f"{self.api_url.rstrip('/')}/v1/workspaces"
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "Connection successful. Workspaces accessible.",
                }
            return {"success": False, "message": f"Postiz API error: {response.text}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Network error: {e}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        if not self.api_url or not self.api_key:
            raise PublishingError("Missing Postiz API URL or API key.")

        url = f"{self.api_url.rstrip('/')}/v1/posts"
        payload = {
            "content": text,
        }
        if media:
            payload["media"] = media

        try:
            response = requests.post(
                url, json=payload, headers=self._get_headers(), timeout=15
            )
            if response.status_code not in [200, 201]:
                raise PublishingError(f"Postiz API error: {response.text}")

            result = response.json()
            post_id = str(result.get("id"))
            public_url = (
                result.get("url") or f"{self.api_url.rstrip('/')}/posts/{post_id}"
            )

            return {
                "post_id": post_id,
                "url": public_url,
            }
        except requests.RequestException as e:
            raise PublishingError(
                f"Network error communicating with Postiz API: {e}"
            ) from e
        except Exception as e:
            raise PublishingError(f"Error publishing to Postiz: {e}") from e

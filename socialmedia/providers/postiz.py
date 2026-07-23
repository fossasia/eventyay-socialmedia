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
            if not self.validate_credentials():
                return {
                    "success": False,
                    "message": (
                        "Postiz connection failed. Workspaces are not accessible."
                    ),
                }

            result = self.publish_post("✅ Connection successful from Eventyay!")
            post_id = result.get("post_id")
            url = result.get("url")
            details = f" Post ID: {post_id}." if post_id else ""
            if url:
                details += f" URL: {url}."
            if not details:
                details = " Postiz accepted the request; check your Postiz posts."
            return {
                "success": True,
                "message": f"Test post created in Postiz.{details}",
            }
        except requests.RequestException as e:
            return {"success": False, "message": f"Network error: {e}"}
        except PublishingError as e:
            return {
                "success": False,
                "message": (
                    "Postiz connection works, but creating a visible test post failed: "
                    f"{e}"
                ),
            }
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
            if response.status_code not in [200, 201, 204]:
                raise PublishingError(f"Postiz API error: {response.text}")

            result = {}
            if response.text and response.text.strip():
                try:
                    result = response.json()
                except ValueError:
                    logger.warning(
                        "Postiz returned a successful non-JSON response: %s",
                        response.text,
                    )

            post_id = result.get("id") or result.get("postId")
            public_url = result.get("url")

            return {
                "post_id": str(post_id) if post_id else "",
                "url": public_url or "",
            }
        except requests.RequestException as e:
            raise PublishingError(
                f"Network error communicating with Postiz API: {e}"
            ) from e
        except Exception as e:
            raise PublishingError(f"Error publishing to Postiz: {e}") from e

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        return [
            "Log in to your Postiz dashboard instance.",
            "Navigate to Settings -> API Keys (or Developer Settings).",
            "Generate a new API Key and copy the value.",
            "Enter your Postiz API instance URL and key to establish connection.",
        ]

import logging
import os
import tempfile
from typing import Any

import requests
from mastodon import Mastodon

from ..utils import validate_safe_url
from .base import BaseSocialProvider, PublishingError

logger = logging.getLogger(__name__)


class MastodonProvider(BaseSocialProvider):
    """Mastodon API integration adapter using Mastodon.py."""

    def __init__(self, account):
        super().__init__(account)
        self.api_base_url = self.credentials.get("api_base_url")
        self.access_token = self.credentials.get("access_token")
        self._client = None

    @property
    def client(self) -> Mastodon:
        if not self._client:
            if not self.api_base_url or not self.access_token:
                raise PublishingError("Missing Mastodon base URL or access token.")
            try:
                self._client = Mastodon(
                    access_token=self.access_token,
                    api_base_url=self.api_base_url,
                )
            except Exception as e:
                raise PublishingError(
                    f"Failed to initialize Mastodon client: {e}"
                ) from e
        return self._client

    def validate_credentials(self) -> bool:
        try:
            self.client.account_verify_credentials()
            return True
        except Exception as e:
            logger.error(f"Mastodon credentials validation failed: {e}")
            return False

    def send_test_message(self) -> dict[str, Any]:
        try:
            self.client.account_verify_credentials()
            self.client.status_post(status="✅ Connection successful from Eventyay!")
            return {"success": True, "message": "Test post published successfully."}
        except Exception as e:
            return {"success": False, "message": f"Mastodon API error: {e}"}

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        try:
            media_ids = []
            if media:
                for file_path in media:
                    if file_path.startswith(("http://", "https://")):
                        validate_safe_url(file_path)
                        r = requests.get(file_path, timeout=20)
                        r.raise_for_status()
                        with tempfile.NamedTemporaryFile(delete=False) as tmp:
                            tmp.write(r.content)
                            tmp_path = tmp.name
                        try:
                            res = self.client.media_post(tmp_path)
                            media_ids.append(res["id"])
                        finally:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                    else:
                        res = self.client.media_post(file_path)
                        media_ids.append(res["id"])

            status = self.client.status_post(
                status=text,
                media_ids=media_ids if media_ids else None,
            )

            post_id = str(status.get("id"))
            url = (
                status.get("url")
                or f"{self.api_base_url}/@{self.account.platform_username}/{post_id}"
            )

            return {
                "post_id": post_id,
                "url": url,
            }

        except Exception as e:
            raise PublishingError(f"Error publishing status to Mastodon: {e}") from e

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        return [
            "Log in to your Mastodon instance page.",
            "Navigate to Preferences -> Development -> New Application.",
            (
                "Give the application a name and ensure it has "
                "'write:statuses' or 'write' scope permissions authorized."
            ),
            "Click Save, click on your new application, and copy the Access Token.",
        ]

import logging
import os
import tempfile
from typing import Any

from mastodon import Mastodon

from ..utils import safe_fetch_url
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
                        r = safe_fetch_url(file_path, timeout=20)
                        r.raise_for_status()

                        content_type = r.headers.get("content-type", "")
                        ext = ".jpg"
                        if "png" in content_type or file_path.lower().endswith(".png"):
                            ext = ".png"
                        elif "gif" in content_type or file_path.lower().endswith(
                            ".gif"
                        ):
                            ext = ".gif"
                        elif "webp" in content_type or file_path.lower().endswith(
                            ".webp"
                        ):
                            ext = ".webp"
                        elif (
                            "jpeg" in content_type
                            or "jpg" in content_type
                            or file_path.lower().endswith((".jpg", ".jpeg"))
                        ):
                            ext = ".jpg"

                        with tempfile.NamedTemporaryFile(
                            suffix=ext, delete=False
                        ) as tmp:
                            tmp.write(r.content)
                            tmp_path = tmp.name
                        try:
                            res = self.client.media_post(
                                tmp_path, mime_type=content_type or None
                            )
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
            (
                "1. Log in to your Mastodon instance (e.g. https://mastodon.social "
                "or your self-hosted instance)."
            ),
            ("2. Go to Preferences → Development → Applications → 'New application'."),
            (
                "3. Fill in:\n"
                "   • Name: Eventyay Social Media\n"
                "   • Scopes: check 'write:statuses' (for posting) and "
                "'read:accounts' (for validation)\n"
                "   • Redirect URI: leave as default\n"
                "   Click 'Submit'."
            ),
            (
                "4. Your application will be created. Click on its name to view "
                "details. Copy the 'Access token' value."
            ),
            (
                "5. Enter below:\n"
                "   • Instance URL: your Mastodon instance URL "
                "(e.g. https://mastodon.social)\n"
                "   • Access Token: the token from step 4\n"
                "   • Username: your full handle (e.g. @myuser@mastodon.social)"
            ),
        ]

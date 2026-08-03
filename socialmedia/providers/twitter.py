import mimetypes
import os
import tempfile
from typing import Any

import requests
from requests_oauthlib import OAuth1

from .base import BaseSocialProvider, PublishingError


class TwitterProvider(BaseSocialProvider):
    """Direct provider adapter for Twitter/X platform using API v2 and Media Upload."""

    MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
    TWEET_API_URL = "https://api.twitter.com/2/tweets"
    VERIFY_API_URL = "https://api.twitter.com/2/users/me"

    def _get_auth(self) -> OAuth1 | None:
        """Construct OAuth1 auth handler if API keys and tokens are provided."""
        api_key = self.credentials.get("api_key") or self.credentials.get(
            "consumer_key"
        )
        api_secret = self.credentials.get("api_secret") or self.credentials.get(
            "consumer_secret"
        )
        access_token = self.credentials.get("access_token")
        access_token_secret = self.credentials.get("access_token_secret")

        if api_key and api_secret and access_token and access_token_secret:
            return OAuth1(
                client_key=api_key,
                client_secret=api_secret,
                resource_owner_key=access_token,
                resource_owner_secret=access_token_secret,
            )
        return None

    def _get_headers(self) -> dict[str, str]:
        """Construct headers for requests. Uses Bearer Token if OAuth1 is not set."""
        headers = {}
        bearer_token = self.credentials.get("bearer_token")
        if bearer_token and not self._get_auth():
            headers["Authorization"] = f"Bearer {bearer_token}"
        return headers

    def validate_credentials(self) -> bool:
        """Verify Twitter API connection by fetching authenticated profile."""
        auth = self._get_auth()
        headers = self._get_headers()

        if not auth and "Authorization" not in headers:
            raise PublishingError(
                "Missing Twitter API credentials. Please provide API Key, API Secret, "
                "Access Token, and Access Secret."
            )

        try:
            resp = requests.get(
                self.VERIFY_API_URL, auth=auth, headers=headers, timeout=15
            )
            if resp.status_code == 200:
                return True
            err_msg = resp.json().get("detail") or resp.text
            raise PublishingError(
                f"Twitter API authentication failed ({resp.status_code}): {err_msg}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Could not connect to Twitter API: {e}") from e

    def _upload_media(self, media_item: str) -> str:
        """Upload image file or URL to Twitter Media Upload API (v1.1)."""
        auth = self._get_auth()
        headers = self._get_headers()

        try:
            if media_item.startswith(("http://", "https://")):
                res = requests.get(media_item, timeout=20)
                res.raise_for_status()
                content = res.content
                content_type = res.headers.get("Content-Type", "")

                ext = (
                    mimetypes.guess_extension(content_type.split(";")[0].strip())
                    or ".jpg"
                )
                filename = f"twitter_upload{ext}"

                with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
                    tmp.write(content)
                    tmp.flush()
                    tmp.seek(0)
                    files = {"media": (filename, tmp, content_type or "image/jpeg")}
                    resp = requests.post(
                        self.MEDIA_UPLOAD_URL,
                        files=files,
                        auth=auth,
                        headers=headers,
                        timeout=30,
                    )
            else:
                file_path = media_item
                if not os.path.exists(file_path):
                    try:
                        from django.conf import settings

                        if hasattr(settings, "MEDIA_ROOT") and settings.MEDIA_ROOT:
                            rel_path = media_item.lstrip("/")
                            if rel_path.startswith("media/"):
                                rel_path = rel_path[6:]
                            possible_path = os.path.join(settings.MEDIA_ROOT, rel_path)
                            if os.path.exists(possible_path):
                                file_path = possible_path
                    except Exception:
                        pass

                with open(file_path, "rb") as f:
                    mime_type, _ = mimetypes.guess_type(file_path)
                    files = {
                        "media": (
                            os.path.basename(file_path),
                            f,
                            mime_type or "image/jpeg",
                        )
                    }
                    resp = requests.post(
                        self.MEDIA_UPLOAD_URL,
                        files=files,
                        auth=auth,
                        headers=headers,
                        timeout=30,
                    )

            if resp.status_code in (200, 201):
                data = resp.json()
                media_id = data.get("media_id_string")
                if media_id:
                    return media_id
                raise PublishingError(
                    "Twitter media upload response missing media_id_string: "
                    f"{resp.text}"
                )
            raise PublishingError(
                f"Twitter media upload failed ({resp.status_code}): {resp.text}"
            )
        except Exception as e:
            if isinstance(e, PublishingError):
                raise
            raise PublishingError(f"Failed to upload image to Twitter: {e}") from e

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        """Publish a tweet with optional image attachments to Twitter API v2.

        Args:
            text (str): Tweet copy text (max 280 chars).
            media (list[str] | None): Optional list of image URLs or file paths.

        Returns:
            dict[str, Any]: Contains 'post_id' and 'url' of the published tweet.
        """
        auth = self._get_auth()
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        if not auth and "Authorization" not in headers:
            raise PublishingError(
                "Missing Twitter API credentials. Please provide API Key, API Secret, "
                "Access Token, and Access Secret."
            )

        media_ids = []
        fallback_urls = []
        if media:
            for item in media:
                if item:
                    try:
                        media_id = self._upload_media(item)
                        media_ids.append(media_id)
                    except Exception:
                        if item.startswith(("http://", "https://")):
                            fallback_urls.append(item)

        tweet_text = text
        if fallback_urls and not media_ids:
            tweet_text = f"{text}\n\n{' '.join(fallback_urls)}"

        payload: dict[str, Any] = {"text": tweet_text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}

        try:
            resp = requests.post(
                self.TWEET_API_URL,
                json=payload,
                auth=auth,
                headers=headers,
                timeout=20,
            )
            if resp.status_code in (200, 201):
                data = resp.json().get("data", {})
                tweet_id = data.get("id")
                username = self.account.platform_username or "i"
                user_handle = username.lstrip("@")
                tweet_url = (
                    f"https://x.com/{user_handle}/status/{tweet_id}" if tweet_id else ""
                )
                return {"post_id": tweet_id, "url": tweet_url}

            err_msg = resp.json().get("detail") or resp.text
            raise PublishingError(
                f"Twitter API returned error ({resp.status_code}): {err_msg}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Error publishing tweet to Twitter: {e}") from e

    def send_test_message(self) -> dict[str, Any]:
        """Send a test tweet to verify connection and credentials."""
        result = self.publish_post("Test message from Eventyay Social Media plugin.")
        tweet_id = result.get("post_id")
        return {
            "success": True,
            "message": f"Test tweet published successfully! Tweet ID: {tweet_id}",
            "url": result.get("url"),
        }

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        return [
            "Go to Twitter Developer Portal (https://developer.x.com) and log in.",
            "Create a new Project and App under your Developer Account.",
            (
                "Set User Authentication Settings to 'Read and write' permissions "
                "and App Type to 'Web App' or 'Automated App'."
            ),
            (
                "Generate your API Key, API Secret, User Access Token, and User "
                "Access Token Secret from the 'Keys and Tokens' tab."
            ),
            (
                "Enter your 4 API credentials into the Eventyay Social Media "
                "Account settings form."
            ),
        ]

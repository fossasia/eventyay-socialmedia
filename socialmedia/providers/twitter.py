import mimetypes
import os
import tempfile
from typing import Any

import requests
from requests_oauthlib import OAuth1

from .base import BaseSocialProvider, PublishingError, _safe_fetch_url, _try_local_media_fallback


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

    @staticmethod
    def _safe_open_local(media_item: str) -> tuple[bytes, str, str]:
        """Open a local media path safely, confined to MEDIA_ROOT.

        Returns:
            (content bytes, mime_type string, filename string)

        Raises:
            PublishingError: If the path escapes MEDIA_ROOT or the file does not exist.
        """
        from django.conf import settings

        media_root = getattr(settings, "MEDIA_ROOT", None)
        if not media_root:
            raise PublishingError(
                "MEDIA_ROOT is not configured; cannot open local media files."
            )

        rel_path = media_item.lstrip("/")
        if rel_path.startswith("media/"):
            rel_path = rel_path[6:]
        candidate = os.path.join(media_root, rel_path)

        # Resolve symlinks / ".." traversal
        real_candidate = os.path.realpath(candidate)
        real_root = os.path.realpath(media_root)

        if not real_candidate.startswith(real_root + os.sep) and real_candidate != real_root:
            raise PublishingError(
                f"Access denied: {media_item!r} resolves outside MEDIA_ROOT."
            )
        if not os.path.isfile(real_candidate):
            raise PublishingError(f"Media file not found: {real_candidate!r}")

        mime_type, _ = mimetypes.guess_type(real_candidate)
        with open(real_candidate, "rb") as f:
            content = f.read()
        return content, mime_type or "image/jpeg", os.path.basename(real_candidate)

    def _upload_media(self, media_item: str) -> str:
        """Upload image file or URL to Twitter Media Upload API (v1.1).

        .. note::
            Twitter's v1.1 Media Upload endpoint requires OAuth1 user-context
            authentication. Bearer tokens are rejected with HTTP 403. All four
            OAuth1 credentials (API Key, API Secret, Access Token, Access Token
            Secret) must be configured for media uploads to work.
        """
        auth = self._get_auth()
        if not auth:
            raise PublishingError(
                "Twitter media upload requires OAuth1 credentials (API Key, API Secret, "
                "Access Token, Access Token Secret). The v1.1 media upload endpoint does "
                "not accept Bearer tokens. Please configure all four OAuth1 credentials."
            )
        # Strip Authorization header for v1.1 upload endpoint — only OAuth1 sig is accepted.
        upload_headers = {}

        try:
            if media_item.startswith(("http://", "https://")):
                # SSRF guard: blocks private/link-local IPs and caps response size.
                # Falls back to reading from MEDIA_ROOT if the URL points to our
                # own server (e.g. localhost in dev, or SITE_URL on the same host).
                try:
                    res = _safe_fetch_url(media_item, timeout=20)
                    content = res.content
                    content_type = res.headers.get("Content-Type", "")
                except ValueError as exc:
                    local = _try_local_media_fallback(media_item)
                    if local is None:
                        raise PublishingError(
                            f"Refused to fetch media URL: {exc}"
                        ) from exc
                    content, content_type = local

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
                        headers=upload_headers,
                        timeout=30,
                    )
            else:
                # Path traversal guard: confined to MEDIA_ROOT.
                content, mime_type, filename = self._safe_open_local(media_item)
                with tempfile.NamedTemporaryFile(
                    suffix=os.path.splitext(filename)[1], delete=True
                ) as tmp:
                    tmp.write(content)
                    tmp.flush()
                    tmp.seek(0)
                    files = {"media": (filename, tmp, mime_type)}
                    resp = requests.post(
                        self.MEDIA_UPLOAD_URL,
                        files=files,
                        auth=auth,
                        headers=upload_headers,
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
                    except PublishingError:
                        # Re-raise credential/config errors — these need the organizer's attention.
                        raise
                    except Exception:
                        # Transient failure (network, etc.): fall back to URL in tweet text.
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
        """Send a test tweet to verify connection and credentials.

        .. warning::
            This publishes a **real, public tweet** on Twitter/X. Only call this
            when the organizer explicitly requests a test and understands that
            the tweet will be publicly visible.
        """
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
            (
                "1. Go to https://developer.x.com and log in with your "
                "Twitter/X account."
            ),
            (
                "2. If you don't have a developer account, click 'Sign up' and "
                "agree to the developer terms. Free tier supports basic posting."
            ),
            (
                "3. Create a new Project (if you don't have one) → then create "
                "an App under that project."
            ),
            (
                "4. In your App settings, go to 'User authentication settings' → "
                "click 'Edit'. Set:\n"
                "   • App permissions: 'Read and write'\n"
                "   • Type of App: 'Web App, Automated App or Bot'\n"
                "   • Callback URL: https://localhost\n"
                "   • Website URL: https://localhost\n"
                "   Click 'Save'."
            ),
            (
                "5. Go to 'Keys and tokens' tab. Under 'Consumer Keys', click "
                "'Regenerate' to get your API Key and API Secret. Under "
                "'Authentication Tokens', click 'Generate' under 'Access Token "
                "and Secret' to get your Access Token and Access Token Secret. "
                "Make sure the token shows 'Read and write' permissions."
            ),
            (
                "6. Enter all 4 credentials below:\n"
                "   • API Key (Consumer Key)\n"
                "   • API Secret (Consumer Secret)\n"
                "   • Access Token\n"
                "   • Access Token Secret\n"
                "   Also enter your Twitter/X handle (e.g. @eventyay)."
            ),
        ]

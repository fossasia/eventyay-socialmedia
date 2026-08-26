import logging
import mimetypes
import os
import re
from datetime import UTC, datetime
from typing import Any

import requests

from .base import (
    BaseSocialProvider,
    PublishingError,
    _safe_fetch_url,
    _try_local_media_fallback,
)

logger = logging.getLogger(__name__)


def extract_atproto_facets(text: str) -> list[dict[str, Any]]:
    """Extract URL links and hashtags as AT Protocol richtext facets with
    UTF-8 byte offsets.

    Bluesky AT Protocol requires byte indices (not Unicode character offsets)
    for facets:
    - URLs: app.bsky.richtext.facet#link
    - Hashtags: app.bsky.richtext.facet#tag
    """
    if not text:
        return []

    facets = []

    # 1. Match URLs
    url_pattern = re.compile(r"https?://[^\s]+")
    for match in url_pattern.finditer(text):
        uri = match.group(0)
        # Strip trailing punctuation that is likely not part of the URL
        while uri and uri[-1] in ".,!?:;)'\"]":
            uri = uri[:-1]
        if not uri:
            continue

        start_char = match.start()
        end_char = start_char + len(uri)

        byte_start = len(text[:start_char].encode("utf-8"))
        byte_end = len(text[:end_char].encode("utf-8"))

        facets.append(
            {
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": uri,
                    }
                ],
            }
        )

    # 2. Match Hashtags
    # Match words preceded by # starting at word boundary or start of string
    tag_pattern = re.compile(r"(?:^|\s)(#[a-zA-Z0-9_]+)")
    for match in tag_pattern.finditer(text):
        full_match = match.group(1)  # e.g. #eventyay
        tag_name = full_match.lstrip("#")
        if not tag_name:
            continue

        start_char = match.start(1)
        end_char = match.end(1)

        byte_start = len(text[:start_char].encode("utf-8"))
        byte_end = len(text[:end_char].encode("utf-8"))

        facets.append(
            {
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#tag",
                        "tag": tag_name,
                    }
                ],
            }
        )

    # Sort facets by byteStart
    facets.sort(key=lambda f: f["index"]["byteStart"])
    return facets


class BlueskyProvider(BaseSocialProvider):
    """Direct provider adapter for Bluesky using the AT Protocol (atproto) XRPC API."""

    DEFAULT_PDS_URL = "https://bsky.social"

    def _get_pds_url(self) -> str:
        """Return the configured PDS URL or default bsky.social."""
        url = self.credentials.get("pds_url") or self.DEFAULT_PDS_URL
        return url.strip().rstrip("/")

    def _get_identifier(self) -> str:
        """Return the handle or identifier from credentials or platform_username."""
        handle = self.credentials.get("handle") or self.account.platform_username or ""
        return handle.strip().lstrip("@")

    def _get_app_password(self) -> str:
        """Return the app password from credentials."""
        return (self.credentials.get("app_password") or "").strip()

    def _create_session(self) -> dict[str, Any]:
        """Authenticate with the AT Protocol PDS and return session data.

        Returns:
            dict containing 'accessJwt', 'did', 'handle', etc.

        Raises:
            PublishingError: If authentication fails or credentials are missing.
        """
        identifier = self._get_identifier()
        password = self._get_app_password()
        pds_url = self._get_pds_url()

        if not identifier or not password:
            raise PublishingError(
                "Missing Bluesky handle or App Password in credentials."
            )

        endpoint = f"{pds_url}/xrpc/com.atproto.server.createSession"
        try:
            resp = requests.post(
                endpoint,
                json={"identifier": identifier, "password": password},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()

            try:
                err_data = resp.json()
                err_msg = err_data.get("message") or err_data.get("error") or resp.text
            except Exception:
                err_msg = resp.text[:200]

            raise PublishingError(
                f"Bluesky authentication failed ({resp.status_code}): {err_msg}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Could not connect to Bluesky PDS: {e}") from e

    def validate_credentials(self) -> bool:
        """Verify the Bluesky connection status by creating an authenticated session.

        Returns:
            bool: True if authentication succeeds, False otherwise.
        """
        try:
            session = self._create_session()
            return bool(session.get("accessJwt"))
        except Exception as e:
            logger.error("Bluesky credentials validation failed: %s", e)
            return False

    @staticmethod
    def _safe_open_local(media_item: str) -> tuple[bytes, str]:
        """Open a local media path safely, confined to MEDIA_ROOT."""
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

        real_candidate = os.path.realpath(candidate)
        real_root = os.path.realpath(media_root)

        if (
            not real_candidate.startswith(real_root + os.sep)
            and real_candidate != real_root
        ):
            raise PublishingError(
                f"Access denied: {media_item!r} resolves outside MEDIA_ROOT."
            )
        if not os.path.isfile(real_candidate):
            raise PublishingError(f"Media file not found: {real_candidate!r}")

        mime_type, _ = mimetypes.guess_type(real_candidate)
        with open(real_candidate, "rb") as f:
            content = f.read()
        return content, mime_type or "image/jpeg"

    def _upload_media_blob(
        self, access_jwt: str, pds_url: str, media_item: str
    ) -> dict[str, Any]:
        """Fetch/read media and upload as an AT Protocol blob.

        Returns:
            dict: The 'blob' object from com.atproto.repo.uploadBlob response.
        """
        if media_item.startswith(("http://", "https://")):
            try:
                res = _safe_fetch_url(media_item, timeout=20)
                content = res.content
                content_type = res.headers.get("Content-Type", "") or "image/jpeg"
            except ValueError as exc:
                local = _try_local_media_fallback(media_item)
                if local is None:
                    raise PublishingError(f"Refused to fetch media URL: {exc}") from exc
                content, content_type = local
        else:
            content, content_type = self._safe_open_local(media_item)

        # Clean content_type if it contains charset
        if ";" in content_type:
            content_type = content_type.split(";")[0].strip()
        if not content_type:
            content_type = "image/jpeg"

        upload_url = f"{pds_url}/xrpc/com.atproto.repo.uploadBlob"
        headers = {
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": content_type,
        }

        try:
            resp = requests.post(
                upload_url,
                data=content,
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                blob = data.get("blob")
                if blob:
                    return blob
                raise PublishingError(
                    f"Bluesky media upload response missing blob: {resp.text}"
                )

            try:
                err_msg = resp.json().get("message") or resp.text
            except Exception:
                err_msg = resp.text[:200]
            raise PublishingError(
                f"Bluesky media upload failed ({resp.status_code}): {err_msg}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Error uploading media blob to Bluesky: {e}") from e

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        """Publish a post to Bluesky using com.atproto.repo.createRecord.

        Args:
            text (str): Post text (max 300 characters).
            media (list[str] | None): Optional image attachments.

        Returns:
            dict[str, Any]: Contains 'post_id' and 'url' of the published post.
        """
        session = self._create_session()
        access_jwt = session["accessJwt"]
        did = session["did"]
        handle = session.get("handle") or self._get_identifier()
        pds_url = self._get_pds_url()

        # 1. Parse richtext facets
        facets = extract_atproto_facets(text)

        # 2. Upload media if present (up to 4 images supported on Bluesky)
        embed = None
        if media:
            images = []
            for item in media[:4]:
                if not item:
                    continue
                try:
                    blob = self._upload_media_blob(access_jwt, pds_url, item)
                    images.append(
                        {
                            "alt": "",
                            "image": blob,
                        }
                    )
                except Exception as exc:
                    logger.warning("Bluesky media upload failed for %s: %s", item, exc)
                    if isinstance(exc, PublishingError):
                        raise

            if images:
                embed = {
                    "$type": "app.bsky.embed.images",
                    "images": images,
                }

        # 3. Build post record
        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        record: dict[str, Any] = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now_iso,
        }
        if facets:
            record["facets"] = facets
        if embed:
            record["embed"] = embed

        # 4. Create record via AT Protocol
        create_url = f"{pds_url}/xrpc/com.atproto.repo.createRecord"
        headers = {
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": "application/json",
        }
        payload = {
            "repo": did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        try:
            resp = requests.post(
                create_url,
                json=payload,
                headers=headers,
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                uri = data.get("uri", "")  # at://did:plc:.../app.bsky.feed.post/3l...
                rkey = uri.split("/")[-1] if uri else ""
                post_url = (
                    f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else ""
                )
                return {
                    "post_id": rkey or uri,
                    "url": post_url,
                }

            try:
                err_data = resp.json()
                err_msg = err_data.get("message") or err_data.get("error") or resp.text
            except Exception:
                err_msg = resp.text[:200]
            raise PublishingError(
                f"Bluesky post creation failed ({resp.status_code}): {err_msg}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Error publishing post to Bluesky: {e}") from e

    def send_test_message(self) -> dict[str, Any]:
        """Send a test post to Bluesky to verify connection."""
        result = self.publish_post("Test message from Eventyay Social Media plugin.")
        post_id = result.get("post_id")
        return {
            "success": True,
            "message": (
                f"Test post published successfully to Bluesky! Post ID: {post_id}"
            ),
            "url": result.get("url"),
        }

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        return [
            "1. Log in to your Bluesky account at https://bsky.app.",
            "2. Go to Settings → Advanced → 'App passwords'.",
            (
                "3. Click 'Add App Password', give it a name (e.g. 'Eventyay'), "
                "and click 'Create App Password'."
            ),
            (
                "4. Copy the generated App Password (format: xxxx-xxxx-xxxx-xxxx). "
                "Do not use your main account password."
            ),
            (
                "5. Enter below:\n"
                "   • Bluesky Handle: your username (e.g. user.bsky.social)\n"
                "   • App Password: the password generated in step 4\n"
                "   • PDS URL: https://bsky.social (or custom PDS host)"
            ),
        ]

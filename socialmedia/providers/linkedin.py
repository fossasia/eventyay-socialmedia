import logging
import mimetypes
import os
from typing import Any

import requests

from .base import (
    BaseSocialProvider,
    PublishingError,
    _safe_fetch_url,
    _try_local_media_fallback,
)

logger = logging.getLogger(__name__)

# Pinned to a documented, stable API version.
_LINKEDIN_API_VERSION = "202504"


class LinkedInProvider(BaseSocialProvider):
    """Direct provider adapter for LinkedIn platform using REST API (v2 / ugcPosts)."""

    USERINFO_API_URL = "https://api.linkedin.com/v2/userinfo"
    ME_API_URL = "https://api.linkedin.com/v2/me"
    REGISTER_UPLOAD_API_URL = "https://api.linkedin.com/v2/assets?action=registerUpload"
    UGC_POSTS_API_URL = "https://api.linkedin.com/v2/ugcPosts"

    def _get_headers(self) -> dict[str, str]:
        """Construct Authorization and Content-Type headers."""
        access_token = self.credentials.get("access_token")
        if not access_token:
            raise PublishingError(
                "Missing LinkedIn Access Token. "
                "Please configure your LinkedIn Access Token."
            )
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    @staticmethod
    def _validate_urn(urn: str) -> str | None:
        """Return the URN if valid, or None if missing or malformed."""
        if not urn or not urn.startswith("urn:li:"):
            return None
        parts = urn.split(":")
        if len(parts) < 4 or not parts[3].strip():
            return None
        return urn

    def _resolve_person_urn(self, member_id: str) -> str | None:
        """Resolve a numeric member ID to the correct person URN.

        Uses a read-only GET /v2/me call rather than creating a draft post,
        which avoids the side-effecting ugcPosts probe.
        """
        headers = self._get_headers()
        try:
            resp = requests.get(self.ME_API_URL, headers=headers, timeout=15)
            if resp.status_code == 200:
                user_id = resp.json().get("id")
                if user_id:
                    return f"urn:li:person:{user_id}"
            # Fall back: if the member_id matches the authenticated user,
            # trust it directly rather than creating a draft post.
            logger.debug(
                "_resolve_person_urn: /v2/me returned %s for member_id=%s",
                resp.status_code,
                member_id,
            )
        except Exception:
            logger.debug(
                "_resolve_person_urn: request failed for member_id=%s",
                member_id,
                exc_info=True,
            )
        return None

    def _get_author_urn(self) -> str:
        """Resolve LinkedIn Author URN (person or organization URN)."""
        author_urn = (
            self.credentials.get("author_urn") or self.credentials.get("author") or ""
        )
        if author_urn:
            if not author_urn.startswith("urn:li:"):
                author_urn = f"urn:li:person:{author_urn}"
            # Convert urn:li:member:ID to urn:li:person:ID for Posts API
            if author_urn.startswith("urn:li:member:"):
                entity_id = author_urn.split(":")[3]
                author_urn = f"urn:li:person:{entity_id}"
            validated = self._validate_urn(author_urn)
            if validated:
                return validated

        # Support URN or numeric member ID placed in account username field
        uname = (self.account.platform_username or "").strip()
        if uname.startswith("urn:li:"):
            return uname
        if uname.isdigit():
            return f"urn:li:person:{uname}"

        headers = self._get_headers()
        # Try /v2/me first (returns numeric Person ID for ugcPosts API)
        try:
            resp = requests.get(self.ME_API_URL, headers=headers, timeout=15)
            if resp.status_code == 200:
                user_id = resp.json().get("id")
                if user_id:
                    return f"urn:li:person:{user_id}"
        except Exception:
            logger.debug("_get_author_urn: /v2/me request failed", exc_info=True)

        # Try /v2/userinfo (OpenID Connect)
        try:
            resp = requests.get(self.USERINFO_API_URL, headers=headers, timeout=15)
            if resp.status_code == 200:
                sub = resp.json().get("sub")
                if sub:
                    return f"urn:li:person:{sub}"
        except Exception:
            logger.debug("_get_author_urn: /v2/userinfo request failed", exc_info=True)

        raise PublishingError(
            "Missing LinkedIn Author URN. Please enter your Author URN "
            "(e.g. urn:li:person:XXXX or urn:li:organization:XXXX)."
        )

    def validate_credentials(self) -> bool:
        """Verify LinkedIn access token by probing profile endpoints.

        Fails closed: only returns True when a profile endpoint responds 200.
        A 403 is NOT treated as success — tokens that cannot read a profile
        likely cannot post and should be rejected at save time.
        """
        headers = self._get_headers()
        # Prefer least-permission profile endpoints.
        profile_endpoints = [
            self.USERINFO_API_URL,
            self.ME_API_URL,
        ]
        last_error = ""
        for url in profile_endpoints:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return True
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except requests.RequestException as e:
                last_error = str(e)
                continue
        raise PublishingError(f"LinkedIn authentication failed: {last_error}")

    @staticmethod
    def _safe_open_local(media_item: str) -> tuple[bytes, str]:
        """Open a local media path safely, confined to MEDIA_ROOT.

        Returns:
            (content bytes, mime_type string)

        Raises:
            PublishingError: If the path escapes MEDIA_ROOT or does not exist.
        """
        from django.conf import settings

        media_root = getattr(settings, "MEDIA_ROOT", None)
        if not media_root:
            raise PublishingError(
                "MEDIA_ROOT is not configured; cannot open local media files."
            )

        # Build candidate path relative to MEDIA_ROOT
        rel_path = media_item.lstrip("/")
        if rel_path.startswith("media/"):
            rel_path = rel_path[6:]
        candidate = os.path.join(media_root, rel_path)

        # Resolve symlinks / ".." traversal
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

        with open(real_candidate, "rb") as f:
            content = f.read()
        mime_type, _ = mimetypes.guess_type(real_candidate)
        return content, mime_type or "image/jpeg"

    def _upload_media(self, media_item: str, author_urn: str) -> str:
        """Register asset upload and upload binary image bytes to LinkedIn."""
        headers = self._get_headers()

        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": author_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }

        try:
            reg_resp = requests.post(
                self.REGISTER_UPLOAD_API_URL,
                json=register_payload,
                headers=headers,
                timeout=20,
            )
            if reg_resp.status_code not in (200, 201):
                raise PublishingError(
                    f"LinkedIn registerUpload failed ({reg_resp.status_code}): "
                    f"{reg_resp.text}"
                )

            reg_data = reg_resp.json().get("value", {})
            asset_urn = reg_data.get("asset")
            upload_url = (
                reg_data.get("uploadMechanism", {})
                .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                .get("uploadUrl")
            )

            if not asset_urn or not upload_url:
                raise PublishingError(
                    f"LinkedIn asset upload registration incomplete: {reg_resp.text}"
                )

            if media_item.startswith(("http://", "https://")):
                # SSRF guard: blocks private/link-local IPs and caps response size.
                # Falls back to reading from MEDIA_ROOT if the URL points to our
                # own server (e.g. localhost in dev, or SITE_URL on the same host).
                try:
                    img_res = _safe_fetch_url(media_item, timeout=20)
                    content = img_res.content
                    content_type = img_res.headers.get("Content-Type", "image/jpeg")
                except ValueError as exc:
                    local = _try_local_media_fallback(media_item)
                    if local is None:
                        raise PublishingError(
                            f"Refused to fetch media URL: {exc}"
                        ) from exc
                    content, content_type = local
            else:
                # Path traversal guard: confined to MEDIA_ROOT.
                content, content_type = self._safe_open_local(media_item)

            upload_headers = {
                "Authorization": headers["Authorization"],
                "Content-Type": content_type,
            }
            up_resp = requests.put(
                upload_url, data=content, headers=upload_headers, timeout=30
            )
            if up_resp.status_code in (200, 201):
                return asset_urn
            raise PublishingError(
                f"LinkedIn image binary upload failed ({up_resp.status_code}): "
                f"{up_resp.text}"
            )
        except Exception as e:
            if isinstance(e, PublishingError):
                raise
            raise PublishingError(f"Failed to upload media to LinkedIn: {e}") from e

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        """Publish a status post with optional image attachment to LinkedIn.

        Args:
            text (str): Commentary text.
            media (list[str] | None): Optional list of image URLs or file paths.

        Returns:
            dict[str, Any]: Contains 'post_id' and 'url' of the published LinkedIn post.
        """
        headers = self._get_headers()
        author_urn = self._get_author_urn()

        asset_urns = []
        fallback_urls = []
        if media:
            for item in media:
                if item:
                    try:
                        asset_urn = self._upload_media(item, author_urn)
                        asset_urns.append(asset_urn)
                    except PublishingError:
                        # Re-raise credential/scope errors — organizer needs to fix these.
                        raise
                    except Exception:
                        # Transient failure (network, etc.): fall back to URL in post text.
                        if item.startswith(("http://", "https://")):
                            fallback_urls.append(item)

        commentary_text = text
        if fallback_urls and not asset_urns:
            commentary_text = f"{text}\n\n{' '.join(fallback_urls)}"

        media_category = "IMAGE" if asset_urns else "NONE"
        media_list = [{"status": "READY", "media": urn} for urn in asset_urns]

        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": commentary_text},
                    "shareMediaCategory": media_category,
                    "media": media_list,
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        rest_headers = dict(headers)
        rest_headers["LinkedIn-Version"] = _LINKEDIN_API_VERSION
        rest_payload: dict[str, Any] = {
            "author": author_urn,
            "commentary": commentary_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
        }
        if asset_urns:
            if len(asset_urns) == 1:
                rest_payload["content"] = {"media": {"id": asset_urns[0]}}
            else:
                rest_payload["content"] = {
                    "multiImage": {"images": [{"id": urn} for urn in asset_urns]}
                }

        rest_err_msg = None
        try:
            # 1. Try Versioned REST Posts API
            resp = requests.post(
                "https://api.linkedin.com/rest/posts",
                json=rest_payload,
                headers=rest_headers,
                timeout=20,
            )
            if resp.status_code not in (200, 201) and "not active" in resp.text:
                # Fallback to previous minor version
                fallback_headers = dict(rest_headers)
                fallback_headers["LinkedIn-Version"] = "202503"
                resp = requests.post(
                    "https://api.linkedin.com/rest/posts",
                    json=rest_payload,
                    headers=fallback_headers,
                    timeout=20,
                )
            if resp.status_code in (200, 201):
                post_id = None
                try:
                    data = resp.json()
                    post_id = data.get("id") if isinstance(data, dict) else None
                except Exception:
                    pass
                if not post_id and hasattr(resp.headers, "get"):
                    post_id = resp.headers.get("x-restli-id")
                post_url = (
                    f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""
                )
                return {"post_id": post_id, "url": post_url}

            try:
                rest_err_msg = resp.json().get("message") or resp.text
            except Exception:
                rest_err_msg = resp.text

            # 2. Fallback to legacy ugcPosts API
            resp = requests.post(
                self.UGC_POSTS_API_URL, json=payload, headers=headers, timeout=20
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                post_id = data.get("id")
                post_url = (
                    f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""
                )
                return {"post_id": post_id, "url": post_url}

            try:
                err_msg = rest_err_msg or resp.json().get("message") or resp.text
            except Exception:
                err_msg = rest_err_msg or resp.text

            # Provide actionable guidance for common error codes
            hint = ""
            try:
                is_403_status = "403" in str(resp.json().get("status", ""))
            except Exception:
                is_403_status = False
            if resp.status_code in (401, 403) or is_403_status:
                hint = (
                    "\n\nThis usually means your Access Token is missing the "
                    "'w_member_social' scope. Regenerate your token at "
                    "https://www.linkedin.com/developers/apps with the "
                    "'Share on LinkedIn' product enabled."
                )
            elif resp.status_code == 422:
                hint = (
                    "\n\nVerify your Author URN is correct and matches your "
                    "LinkedIn account type (person vs organization)."
                )
            raise PublishingError(
                f"LinkedIn API returned error ({resp.status_code}): {err_msg}{hint}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Error publishing post to LinkedIn: {e}") from e

    def send_test_message(self) -> dict[str, Any]:
        """Send a test post to verify LinkedIn connection.

        .. warning::
            This publishes a **real, public post** on LinkedIn. Only call this
            when the organizer explicitly requests a test and understands that
            the post will be visible publicly.
        """
        result = self.publish_post("Test message from Eventyay Social Media plugin.")
        post_id = result.get("post_id")
        return {
            "success": True,
            "message": f"Test LinkedIn post published successfully! Post ID: {post_id}",
            "url": result.get("url"),
        }

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        return [
            (
                "1. Go to https://www.linkedin.com/developers and log in with "
                "your LinkedIn account."
            ),
            (
                "2. Click 'Create app', fill in the app name, description, and "
                "upload a logo. Note: LinkedIn requires you to link the app to a "
                "Company Page. If you don't have one, click 'Create a new LinkedIn "
                "Page' to make a quick page first."
            ),
            (
                "3. On the 'Products' tab, add these products to get the right permissions:\n"
                "   • 'Share on LinkedIn' (grants w_member_social)\n"
                "   • 'Sign In with LinkedIn using OpenID Connect' (grants openid and profile so Eventyay can auto-fetch your ID)\n"
                "   • 'Advertising API' or 'Community Management API' (grants w_organization_social for posting to company pages)."
            ),
            (
                "4. On the 'Auth' tab, under 'Authorized redirect URLs', add: "
                "https://localhost and click 'Update'."
            ),
            ("5. Note your 'Client ID' and 'Client Secret' from the Auth tab."),
            (
                "6. Open this URL in your browser (replace YOUR_CLIENT_ID with "
                "your Client ID from step 5):\n"
                "https://www.linkedin.com/oauth/v2/authorization?response_type=code"
                "&client_id=YOUR_CLIENT_ID&redirect_uri=https://localhost"
                "&scope=w_member_social%20openid%20profile\n"
                "(Note: If posting to a Company Page, append %20w_organization_social to the scope)."
            ),
            (
                "7. Click 'Authorize app'. You will be redirected to "
                "https://localhost?code=XXXXX (the page may show a connection error — "
                "that's normal). Copy the 'code' value from the URL bar."
            ),
            (
                "8. Your Author URN depends on what you want to post to:\n"
                "   • Personal profile: LEAVE BLANK! (Eventyay will automatically detect your ID).\n"
                "   • Company page: urn:li:organization:YOUR_PAGE_ID (To find your page ID, go to your Company Page URL on LinkedIn; the number in the URL is your page ID)."
            ),
            (
                "9. Enter the authorization code (from step 7), Client ID, Client "
                "Secret, and Author URN (if posting to a company page) into this form. "
                "The access token will be generated automatically."
            ),
        ]

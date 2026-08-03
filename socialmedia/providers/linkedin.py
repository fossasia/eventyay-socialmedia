import mimetypes
import os
from typing import Any

import requests

from .base import BaseSocialProvider, PublishingError


class LinkedInProvider(BaseSocialProvider):
    """Direct provider adapter for LinkedIn platform using REST API (v2 / ugcPosts)."""

    USERINFO_API_URL = "https://api.linkedin.com/v2/userinfo"
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

    def _get_author_urn(self) -> str:
        """Resolve LinkedIn Author URN (person or organization URN)."""
        author_urn = (
            self.credentials.get("author_urn") or self.credentials.get("author") or ""
        )
        if author_urn:
            if not author_urn.startswith("urn:li:"):
                return f"urn:li:person:{author_urn}"
            return author_urn

        # Support URN or numeric member ID placed in account username field
        uname = (self.account.platform_username or "").strip()
        if uname.startswith("urn:li:"):
            return uname
        if uname.isdigit():
            return f"urn:li:person:{uname}"

        headers = self._get_headers()
        # Try /v2/me first (returns numeric Person ID for ugcPosts API)
        try:
            resp = requests.get(
                "https://api.linkedin.com/v2/me", headers=headers, timeout=15
            )
            if resp.status_code == 200:
                user_id = resp.json().get("id")
                if user_id:
                    return f"urn:li:person:{user_id}"
        except Exception:
            pass

        # Try /v2/userinfo (OpenID Connect)
        try:
            resp = requests.get(self.USERINFO_API_URL, headers=headers, timeout=15)
            if resp.status_code == 200:
                sub = resp.json().get("sub")
                if sub:
                    return f"urn:li:person:{sub}"
        except Exception:
            pass

        raise PublishingError(
            "Missing LinkedIn Author URN. Please enter your Author URN "
            "(e.g. urn:li:person:XXXX or urn:li:organization:XXXX)."
        )

    def validate_credentials(self) -> bool:
        """Verify LinkedIn access token by querying userinfo API."""
        headers = self._get_headers()
        try:
            resp = requests.get(self.USERINFO_API_URL, headers=headers, timeout=15)
            if resp.status_code == 200:
                return True
            err_msg = resp.json().get("message") or resp.text
            raise PublishingError(
                f"LinkedIn authentication failed ({resp.status_code}): {err_msg}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Could not connect to LinkedIn API: {e}") from e

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
                err_text = reg_resp.text
                raise PublishingError(
                    f"LinkedIn registerUpload failed ({reg_resp.status_code}): "
                    f"{err_text}"
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
                img_res = requests.get(media_item, timeout=20)
                img_res.raise_for_status()
                content = img_res.content
                content_type = img_res.headers.get("Content-Type", "image/jpeg")
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
                    content = f.read()
                content_type, _ = mimetypes.guess_type(file_path)
                content_type = content_type or "image/jpeg"

            upload_headers = {
                "Authorization": headers["Authorization"],
                "Content-Type": content_type,
            }
            up_resp = requests.put(
                upload_url, data=content, headers=upload_headers, timeout=30
            )
            if up_resp.status_code in (200, 201):
                return asset_urn
            up_text = up_resp.text
            raise PublishingError(
                f"LinkedIn image binary upload failed ({up_resp.status_code}): "
                f"{up_text}"
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
                    except Exception:
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
        rest_headers["LinkedIn-Version"] = "202401"
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
            # 1. Try Versioned REST Posts API (202401)
            resp = requests.post(
                "https://api.linkedin.com/rest/posts",
                json=rest_payload,
                headers=rest_headers,
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

            rest_err_msg = resp.json().get("message") or resp.text

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

            err_msg = rest_err_msg or resp.json().get("message") or resp.text
            raise PublishingError(
                f"LinkedIn API returned error ({resp.status_code}): {err_msg}"
            )
        except requests.RequestException as e:
            raise PublishingError(f"Error publishing post to LinkedIn: {e}") from e

    def send_test_message(self) -> dict[str, Any]:
        """Send a test post to verify LinkedIn connection."""
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
                "Go to LinkedIn Developer Portal "
                "(https://www.linkedin.com/developers) and log in."
            ),
            (
                "Create an App and request 'Share on LinkedIn' (w_member_social) "
                "and 'Sign In with LinkedIn' products."
            ),
            "Generate an Access Token via OAuth 2.0 or Token Generator tool.",
            (
                "Find your Author URN (e.g. urn:li:person:XXXX for member profiles "
                "or urn:li:organization:XXXX for company pages)."
            ),
            (
                "Enter your Access Token and Author URN into the Eventyay Social "
                "Media Account settings form."
            ),
        ]

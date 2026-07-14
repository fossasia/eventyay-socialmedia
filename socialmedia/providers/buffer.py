import json
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
        self.channel_id = self.account.platform_username
        self.base_url = "https://api.buffer.com"

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _graphql(self, query: str) -> dict[str, Any]:
        if not self.access_token:
            raise PublishingError("Missing Buffer API key.")

        response = requests.post(
            self.base_url,
            json={"query": query},
            headers=self._get_headers(),
            timeout=15,
        )
        if response.status_code != 200:
            raise PublishingError(f"Buffer API error: {response.text}")

        result = response.json()
        if result.get("errors"):
            raise PublishingError(f"Buffer API error: {result['errors']}")
        return result.get("data", {})

    def validate_credentials(self) -> bool:
        try:
            data = self._graphql(
                """
                query ValidateBufferAccount {
                  account {
                    id
                    email
                  }
                }
                """
            )
            return bool(data.get("account"))
        except Exception as e:
            logger.error(f"Buffer credentials validation failed: {e}")
            return False

    def _create_post(self, text: str, *, save_to_draft: bool) -> dict[str, str]:
        if not self.channel_id:
            raise PublishingError("Missing Buffer channel ID.")

        text_value = json.dumps(text)
        channel_id = json.dumps(self.channel_id)
        draft_value = "true" if save_to_draft else "false"
        query = f"""
            mutation CreateEventyayBufferPost {{
              createPost(input: {{
                text: {text_value},
                channelId: {channel_id},
                schedulingType: automatic,
                mode: addToQueue,
                saveToDraft: {draft_value}
              }}) {{
                ... on PostActionSuccess {{
                  post {{
                    id
                    text
                    dueAt
                  }}
                }}
                ... on MutationError {{
                  message
                }}
              }}
            }}
            """

        data = self._graphql(query)
        result = data.get("createPost") or {}
        if result.get("message"):
            raise PublishingError(f"Buffer API error: {result['message']}")

        post = result.get("post") or {}
        post_id = str(post.get("id") or "")
        return {
            "post_id": post_id,
            "url": f"https://publish.buffer.com/content/{post_id}" if post_id else "",
        }

    def send_test_message(self) -> dict[str, Any]:
        if not self.access_token:
            return {"success": False, "message": "Missing API key."}
        try:
            if not self.validate_credentials():
                return {
                    "success": False,
                    "message": "Buffer connection failed. API key is not valid.",
                }

            result = self._create_post(
                "✅ Connection successful from Eventyay!",
                save_to_draft=True,
            )
            details = f" Post ID: {result['post_id']}." if result["post_id"] else ""
            return {
                "success": True,
                "message": f"Test draft created in Buffer.{details}",
            }
        except requests.RequestException as e:
            return {"success": False, "message": f"Network error: {e}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        if not self.access_token or not self.channel_id:
            raise PublishingError("Missing Buffer API key or channel ID.")

        if media:
            logger.warning("Buffer media publishing is not implemented yet.")

        try:
            return self._create_post(text, save_to_draft=False)
        except requests.RequestException as e:
            raise PublishingError(
                f"Network error communicating with Buffer API: {e}"
            ) from e
        except Exception as e:
            raise PublishingError(f"Error publishing to Buffer: {e}") from e

import logging
from typing import Any

from socialmedia.models import SocialMediaAccount

logger = logging.getLogger(__name__)


class PublishingError(Exception):
    """Custom exception raised when post publishing or API sync fails."""

    pass


class BaseSocialProvider:
    """Abstract base class representing a social media or scheduling provider
    integration.
    """

    def __init__(self, account: SocialMediaAccount):
        self.account = account
        self.credentials = account.credentials

    def validate_credentials(self) -> bool:
        """Verify the connection status with the remote platform or aggregator API.

        Returns:
            bool: True if connection is valid, False otherwise.
        """
        raise NotImplementedError(
            "validate_credentials must be implemented by subclasses."
        )

    def publish_post(self, text: str, media: list[str] | None = None) -> dict[str, Any]:
        """Send text copy and media attachments to the provider API.

        Returns:
            Dict[str, Any]: A dict containing 'post_id' and 'url' of the published post.

        Raises:
            PublishingError: If the remote API returns an error or connection fails.
        """
        raise NotImplementedError("publish_post must be implemented by subclasses.")

    def send_test_message(self) -> dict[str, Any]:
        """Send a test message to verify the connection is working.

        Returns:
            Dict[str, Any]: A dict with 'success' (bool) and 'message' (str).

        Raises:
            PublishingError: If the test message fails.
        """
        raise NotImplementedError(
            "send_test_message must be implemented by subclasses."
        )

    def sync_campaign(self, posts: list[Any]) -> list[Any]:
        """(Optional override for schedulers) Batches multiple scheduled posts
        and sends them to the scheduling queue in a single sync session.
        """
        return []

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        """Return a list of step-by-step setup instructions for the provider."""
        return []

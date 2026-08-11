import logging

from eventyay.celery_app import app

from .models import SocialMediaPostStatus
from .providers.registry import get_provider
from .signals import claim_post_for_publishing

logger = logging.getLogger(__name__)


@app.task
def publish_single_post(post_pk: int, provider_name: str):
    """Celery task to publish a single scheduled social media post asynchronously.

    Claims the post using database row locking (select_for_update) and executes
    the provider's publish_post call off the main periodic beat thread.
    """
    claimed_post, account = claim_post_for_publishing(post_pk, provider_name)
    if not claimed_post or not account:
        logger.info(
            f"Post {post_pk} could not be claimed or active account "
            f"missing for provider {provider_name}."
        )
        return

    try:
        provider = get_provider(account)
        media = [claimed_post.media_url] if claimed_post.media_url else None
        provider.publish_post(text=claimed_post.post_text, media=media)
        claimed_post.status = SocialMediaPostStatus.PUBLISHED
        claimed_post.error_message = ""
        claimed_post.save(update_fields=["status", "error_message"])
        logger.info(f"Successfully published post {post_pk} to {provider_name}.")
    except Exception as e:
        logger.error(f"Failed to publish post {post_pk} to {provider_name}: {e}")
        claimed_post.status = SocialMediaPostStatus.FAILED
        claimed_post.error_message = str(e)
        claimed_post.save(update_fields=["status", "error_message"])

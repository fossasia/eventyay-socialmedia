import pytest
from datetime import timedelta
from django.utils.timezone import now
from django_scopes import scope
from unittest.mock import patch

from socialmedia.models import SocialMediaPost, SocialMediaPostStatus, SocialMediaAccount
from socialmedia.signals import publish_scheduled_posts
from socialmedia.providers.telegram import TelegramProvider
from socialmedia.providers.mastodon import MastodonProvider
from socialmedia.providers.base import PublishingError


@pytest.mark.django_db
def test_publish_scheduled_posts_success(organizer, event):
    # Create active account for Telegram
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="telegram",
        platform_username="test_channel",
        is_active=True,
    )
    account.credentials = {"bot_token": "fake_token"}
    account.save()

    # Create due post
    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_1_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Hello Telegram!",
            media_url="https://testserver/img.jpg",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    with patch.object(TelegramProvider, "publish_post", return_value={"post_id": "123", "url": "https://t.me/123"}) as mock_publish:
        publish_scheduled_posts(sender=None)
        
        mock_publish.assert_called_once_with(text="Hello Telegram!", media=["https://testserver/img.jpg"])

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.PUBLISHED
        assert post.error_message == ""


@pytest.mark.django_db
def test_publish_scheduled_posts_failure(organizer, event):
    # Create active account for Mastodon
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="mastodon",
        platform_username="test_user",
        is_active=True,
    )
    account.credentials = {"api_base_url": "https://mastodon.social", "access_token": "fake_token"}
    account.save()

    # Create due post
    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="session",
            entity_id="session_1_mastodon",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Hello Mastodon!",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    with patch.object(MastodonProvider, "publish_post", side_effect=PublishingError("API rate limit exceeded")) as mock_publish:
        publish_scheduled_posts(sender=None)
        
        mock_publish.assert_called_once_with(text="Hello Mastodon!", media=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.FAILED
        assert post.error_message == "API rate limit exceeded"


@pytest.mark.django_db
def test_publish_scheduled_posts_missing_account(organizer, event):
    # No social media accounts created
    
    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="session",
            entity_id="session_1_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Hello Telegram!",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    publish_scheduled_posts(sender=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.FAILED
        assert "No active telegram account found" in post.error_message


@pytest.mark.django_db
def test_publish_scheduled_posts_future_or_other_status(organizer, event):
    # Create active account
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="telegram",
        platform_username="test_channel",
        is_active=True,
    )
    account.credentials = {"bot_token": "fake_token"}
    account.save()

    with scope(organizer=organizer, event=event):
        # Future post
        post_future = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_1_telegram",
            scheduled_at=now() + timedelta(minutes=15),
            post_text="Future Telegram!",
            status=SocialMediaPostStatus.SCHEDULED,
        )
        # Excluded/Draft/Published posts
        post_published = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_2_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Already published!",
            status=SocialMediaPostStatus.PUBLISHED,
        )
        post_generic = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_3_postiz", # postiz (skipped by worker)
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Postiz post!",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    with patch.object(TelegramProvider, "publish_post") as mock_publish:
        publish_scheduled_posts(sender=None)
        mock_publish.assert_not_called()

    with scope(organizer=organizer, event=event):
        post_future.refresh_from_db()
        assert post_future.status == SocialMediaPostStatus.SCHEDULED
        
        post_published.refresh_from_db()
        assert post_published.status == SocialMediaPostStatus.PUBLISHED
        
        post_generic.refresh_from_db()
        assert post_generic.status == SocialMediaPostStatus.SCHEDULED

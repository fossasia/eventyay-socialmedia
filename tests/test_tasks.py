from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils.timezone import now
from django_scopes import scope

from socialmedia.models import (
    SocialMediaAccount,
    SocialMediaPost,
    SocialMediaPostStatus,
)
from socialmedia.providers.base import PublishingError
from socialmedia.providers.mastodon import MastodonProvider
from socialmedia.providers.telegram import TelegramProvider
from socialmedia.signals import publish_scheduled_posts


@pytest.mark.django_db
def test_publish_scheduled_posts_success(organizer, event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
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
            is_pinned=True,
        )

    with patch.object(
        TelegramProvider,
        "publish_post",
        return_value={"post_id": "123", "url": "https://t.me/123"},
    ) as mock_publish:
        publish_scheduled_posts(sender=None)

        mock_publish.assert_called_once_with(
            text="Hello Telegram!", media=["https://testserver/img.jpg"]
        )

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.PUBLISHED
        assert post.error_message == ""


@pytest.mark.django_db
def test_publish_scheduled_posts_failure(organizer, event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    # Create active account for Mastodon
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="mastodon",
        platform_username="test_user",
        is_active=True,
    )
    account.credentials = {
        "api_base_url": "https://mastodon.social",
        "access_token": "fake_token",
    }
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
            is_pinned=True,
        )

    with patch.object(
        MastodonProvider,
        "publish_post",
        side_effect=PublishingError("API rate limit exceeded"),
    ) as mock_publish:
        publish_scheduled_posts(sender=None)

        mock_publish.assert_called_once_with(text="Hello Mastodon!", media=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.FAILED
        assert post.error_message == "API rate limit exceeded"


@pytest.mark.django_db
def test_publish_scheduled_posts_missing_account(organizer, event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    # No social media accounts created

    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="session",
            entity_id="session_1_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Hello Telegram!",
            status=SocialMediaPostStatus.SCHEDULED,
            is_pinned=True,
        )

    publish_scheduled_posts(sender=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.FAILED
        assert "No active telegram account found" in post.error_message


@pytest.mark.django_db
def test_publish_scheduled_posts_future_or_other_status(organizer, event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
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
            is_pinned=True,
        )
        # Excluded/Draft/Published posts
        post_published = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_2_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Already published!",
            status=SocialMediaPostStatus.PUBLISHED,
            is_pinned=True,
        )
        post_generic = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_3_postiz",  # postiz (skipped by worker)
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Postiz post!",
            status=SocialMediaPostStatus.SCHEDULED,
            is_pinned=True,
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


@pytest.mark.django_db
def test_publish_scheduled_posts_auto_publishes_unpinned_posts_when_enabled(
    organizer, event, settings
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="telegram",
        platform_username="test_channel",
        is_active=True,
    )
    account.credentials = {"bot_token": "fake_token"}
    account.save()

    with scope(organizer=organizer, event=event):
        event.settings.set("socialmedia_auto_publish", True)
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_1_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Unpinned auto published post",
            status=SocialMediaPostStatus.SCHEDULED,
            is_pinned=False,
        )

    with patch.object(
        TelegramProvider,
        "publish_post",
        return_value={"post_id": "123", "url": "https://t.me/123"},
    ) as mock_publish:
        publish_scheduled_posts(sender=None)
        mock_publish.assert_called_once_with(text="Unpinned auto published post", media=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.PUBLISHED


@pytest.mark.django_db
def test_publish_scheduled_posts_skips_unpinned_when_auto_publish_disabled(
    organizer, event, settings
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="telegram",
        platform_username="test_channel",
        is_active=True,
    )
    account.credentials = {"bot_token": "fake_token"}
    account.save()

    with scope(organizer=organizer, event=event):
        event.settings.set("socialmedia_auto_publish", False)
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_1_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Unpinned post should be skipped",
            status=SocialMediaPostStatus.SCHEDULED,
            is_pinned=False,
        )

    with patch.object(TelegramProvider, "publish_post") as mock_publish:
        publish_scheduled_posts(sender=None)
        mock_publish.assert_not_called()

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.SCHEDULED


@pytest.mark.django_db
def test_publish_single_post_task_directly(organizer, event):
    from socialmedia.tasks import publish_single_post

    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="telegram",
        platform_username="test_channel",
        is_active=True,
    )
    account.credentials = {"bot_token": "fake_token"}
    account.save()

    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_1_telegram",
            scheduled_at=now() - timedelta(minutes=5),
            post_text="Hello Direct Task!",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    with patch.object(
        TelegramProvider,
        "publish_post",
        return_value={"post_id": "123", "url": "https://t.me/123"},
    ) as mock_publish:
        publish_single_post(post.pk, "telegram")
        mock_publish.assert_called_once_with(text="Hello Direct Task!", media=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.PUBLISHED


@pytest.mark.django_db
def test_safe_fetch_url_ssrf_and_dns_pinning():
    from socialmedia.utils import safe_fetch_url

    with pytest.raises(PublishingError, match="forbidden local address"):
        safe_fetch_url("http://127.0.0.1/test.png")

    with pytest.raises(PublishingError, match="forbidden local address"):
        safe_fetch_url("http://localhost/test.png")

    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.1", 0))]
        with pytest.raises(PublishingError, match="resolved to forbidden IP"):
            safe_fetch_url("http://private-domain.local/image.png")

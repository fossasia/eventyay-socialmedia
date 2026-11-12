import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope

from socialmedia.models import (
    SocialMediaAccount,
    SocialMediaPost,
    SocialMediaPostStatus,
)
from socialmedia.providers.base import PublishingError
from socialmedia.providers.telegram import TelegramProvider
from socialmedia.providers.twitter import TwitterProvider


@pytest.mark.django_db
@pytest.mark.parametrize("is_pinned", [False, True])
def test_regeneration_preserves_published_history(
    logged_in_organizer_client, organizer, event, settings, is_pinned
):
    settings.SITE_URL = "https://testserver"
    route = {"organizer": organizer.slug, "event": event.slug}
    generate_url = reverse("plugins:socialmedia:generate_posts", kwargs=route)
    log_url = reverse("plugins:socialmedia:log", kwargs=route)

    with scope(organizer=organizer, event=event):
        event.date_from = now() + timedelta(days=30)
        event.save()
        for content_type in ("cfp", "speaker", "session", "ticket"):
            event.settings.set(f"socialmedia_{content_type}_enabled", False)
        event.settings.set("socialmedia_schedule_enabled", True)
        event.settings.set("socialmedia_schedule_template", "Original schedule copy")
        event.settings.set("socialmedia_twitter_enabled", True)
        event.settings.set("socialmedia_telegram_enabled", True)

    response = logged_in_organizer_client.post(generate_url)
    assert response.status_code == 200
    assert response.json()["success"]
    with scope(organizer=organizer, event=event):
        published = SocialMediaPost.objects.get(
            event=event, entity_id="schedule_telegram"
        )
        account = SocialMediaAccount.objects.create(
            organizer=organizer,
            provider="telegram",
            platform_username="test-channel",
        )
        account.credentials = {"bot_token": "fake"}
        account.save()
        published.is_pinned = is_pinned
        published.save()

    with patch.object(TelegramProvider, "publish_post") as publish:
        response = logged_in_organizer_client.post(
            reverse("plugins:socialmedia:publish_now", kwargs=route),
            data=json.dumps({"db_id": published.pk}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["success"]
        publish.assert_called_once_with(text="Original schedule copy", media=None)

    with scope(organizer=organizer, event=event):
        published.refresh_from_db()
        assert published.status == SocialMediaPostStatus.PUBLISHED
        original = (
            published.post_text,
            published.scheduled_at,
            published.media_url,
            published.template_context,
            published.updated_at,
        )
        event.date_from += timedelta(days=3)
        event.save()
        event.settings.set("socialmedia_schedule_template", "Revised schedule copy")

    for _ in range(2):
        response = logged_in_organizer_client.post(generate_url)
        assert response.status_code == 200
        assert response.json()["success"]

    response = logged_in_organizer_client.get(log_url, {"status": "published"})
    assert response.status_code == 200
    assert b"Original schedule copy" in response.content
    assert b"Revised schedule copy" not in response.content
    assert response.context["published_count"] == 1

    with scope(organizer=organizer, event=event):
        published.refresh_from_db()
        assert published.status == SocialMediaPostStatus.PUBLISHED
        assert (
            published.post_text,
            published.scheduled_at,
            published.media_url,
            published.template_context,
            published.updated_at,
        ) == original
        scheduled = SocialMediaPost.objects.get(
            event=event, entity_id="schedule_twitter"
        )
        assert scheduled.status == SocialMediaPostStatus.SCHEDULED
        assert scheduled.post_text == "Revised schedule copy"
        assert scheduled.scheduled_at == original[1] + timedelta(days=3)
        assert SocialMediaPost.objects.filter(event=event).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("telegram_succeeds", [True, False])
def test_regeneration_after_failed_multi_provider_publish(
    logged_in_organizer_client, organizer, event, settings, telegram_succeeds
):
    settings.SITE_URL = "https://testserver"
    route = {"organizer": organizer.slug, "event": event.slug}
    generate_url = reverse("plugins:socialmedia:generate_posts", kwargs=route)
    with scope(organizer=organizer, event=event):
        event.date_from = now() + timedelta(days=30)
        event.save()
        for content_type in ("cfp", "speaker", "session", "ticket"):
            event.settings.set(f"socialmedia_{content_type}_enabled", False)
        event.settings.set("socialmedia_schedule_enabled", True)
        event.settings.set("socialmedia_schedule_template", "Original schedule copy")
        # With no platform enabled, generation creates one generic post. The
        # manual publish route sends it to every connected native account.
        for platform in (
            "telegram",
            "twitter",
            "mastodon",
            "linkedin",
            "bluesky",
            "postiz",
            "buffer",
        ):
            event.settings.set(f"socialmedia_{platform}_enabled", False)
        for provider in ("telegram", "twitter"):
            account = SocialMediaAccount.objects.create(
                organizer=organizer, provider=provider, platform_username="test-channel"
            )
            account.credentials = {"bot_token": "fake"}
            account.save()

    assert logged_in_organizer_client.post(generate_url).json()["success"]
    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.get(event=event, entity_id="schedule")

    with (
        patch.object(
            TelegramProvider,
            "publish_post",
            side_effect=None if telegram_succeeds else PublishingError("Offline"),
        ) as telegram,
        patch.object(
            TwitterProvider, "publish_post", side_effect=PublishingError("Offline")
        ) as twitter,
    ):
        response = logged_in_organizer_client.post(
            reverse("plugins:socialmedia:publish_now", kwargs=route),
            data=json.dumps({"db_id": post.pk}),
            content_type="application/json",
        )
        assert response.status_code == 500
        telegram.assert_called_once_with(text="Original schedule copy", media=None)
        twitter.assert_called_once_with(text="Original schedule copy", media=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.FAILED
        assert (
            post.error_message.startswith("Published to (telegram).")
            == telegram_succeeds
        )
        original = (
            post.post_text,
            post.scheduled_at,
            post.updated_at,
            post.error_message,
        )
        event.date_from += timedelta(days=3)
        event.save()
        event.settings.set("socialmedia_schedule_template", "Revised schedule copy")

    for _ in range(2):
        assert logged_in_organizer_client.post(generate_url).json()["success"]
    response = logged_in_organizer_client.get(
        reverse("plugins:socialmedia:log", kwargs=route), {"status": "failed"}
    )
    assert response.status_code == 200
    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.FAILED
        assert post.error_message == original[3]
        if telegram_succeeds:
            assert (
                post.post_text,
                post.scheduled_at,
                post.updated_at,
                post.error_message,
            ) == original
            assert b"Original schedule copy" in response.content
            assert b"Revised schedule copy" not in response.content
        else:
            assert post.post_text == "Revised schedule copy"
            assert post.scheduled_at == original[1] + timedelta(days=3)
            assert b"Revised schedule copy" in response.content
        assert SocialMediaPost.objects.filter(event=event).count() == 1

import json
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope
from eventyay.base.models import Team

from socialmedia.models import (
    SocialMediaAccount,
    SocialMediaPost,
    SocialMediaPostStatus,
)
from socialmedia.signals import control_nav_event_common_socialmedia


@pytest.mark.django_db
def test_navigation_signal_ordering(event, user):
    """Test that sidebar navigation items are ordered: Settings -> Templates -> Posts -> Publishing Log."""
    team = Team.objects.create(
        organizer=event.organizer,
        name="Event Admin Team",
        can_change_event_settings=True,
        all_events=True,
    )
    team.members.add(user)

    settings_url = reverse(
        "plugins:socialmedia:plugin_settings",
        kwargs={"organizer": event.organizer.slug, "event": event.slug},
    )

    class MockRequest:
        def __init__(self):
            self.user = user
            self.path_info = settings_url
            self.session = MagicMock()

    responses = control_nav_event_common_socialmedia(
        sender=event, request=MockRequest()
    )
    assert len(responses) == 1
    children = responses[0]["children"]
    assert len(children) == 4
    labels = [str(r["label"]) for r in children]
    assert "Settings" in labels[0]
    assert "Templates" in labels[1]
    assert "Posts" in labels[2]
    assert "Publishing Log" in labels[3]


@pytest.mark.django_db
def test_templates_view_get(logged_in_organizer_client, organizer, event, settings):
    """Test SocialMediaTemplatesView GET."""
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:templates",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_templates_view_post_valid(
    logged_in_organizer_client, organizer, event, settings
):
    """Test SocialMediaTemplatesView saving custom per-platform templates."""
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:templates",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload = {
        "socialmedia_twitter_cfp_template": "Custom CFP: {cfp_link} {hashtags}",
        "socialmedia_linkedin_cfp_template": "Custom LinkedIn CFP: {event_name} {cfp_link}",
        "socialmedia_telegram_speaker_template": "Custom TG Speaker: {speaker_name}",
        "socialmedia_mastodon_ticket_template": "Custom Mastodon Ticket: {ticket_name}",
    }
    response = logged_in_organizer_client.post(url, payload)
    assert response.status_code == 302

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        event.settings.flush()
        assert (
            event.settings.get("socialmedia_twitter_cfp_template")
            == "Custom CFP: {cfp_link} {hashtags}"
        )
        assert (
            event.settings.get("socialmedia_linkedin_cfp_template")
            == "Custom LinkedIn CFP: {event_name} {cfp_link}"
        )


@pytest.mark.django_db
def test_templates_view_character_limit_validation(
    logged_in_organizer_client, organizer, event, settings
):
    """Test SocialMediaTemplatesView rejects templates that exceed character limits."""
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:templates",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    # Twitter limit is 280 chars
    long_twitter_copy = "x" * 300
    response = logged_in_organizer_client.post(
        url,
        {"socialmedia_twitter_cfp_template": long_twitter_copy},
    )
    assert response.status_code == 200
    assert "form" in response.context
    assert not response.context["form"].is_valid()
    assert "socialmedia_twitter_cfp_template" in response.context["form"].errors


@pytest.mark.django_db
def test_templates_view_save_and_generate(
    logged_in_organizer_client, organizer, event, settings
):
    """Test SocialMediaTemplatesView save_and_generate action."""
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:templates",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.post(
        url,
        {
            "action": "save_and_generate",
            "socialmedia_twitter_cfp_template": "Save and Gen CFP: {cfp_link}",
        },
    )
    assert response.status_code == 302
    assert "posts" in response.url


@pytest.mark.django_db
def test_settings_view_save_and_templates(
    logged_in_organizer_client, organizer, event, settings
):
    """Test SocialMediaPostSettingsView save_and_templates action redirect."""
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:plugin_settings",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.post(
        url,
        {
            "action": "save_and_templates",
            "socialmedia_default_hashtags": "#fossasia #test",
        },
    )
    assert response.status_code == 302
    assert "templates" in response.url


@pytest.mark.django_db
def test_preview_posts_account_metadata(
    logged_in_organizer_client, organizer, event, settings
):
    """Test preview_posts endpoint enriches post payload with account handle and status (Issue #61)."""
    settings.SITE_URL = "https://testserver"

    # Create connected Twitter account
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="twitter",
        platform_username="fossasia_test",
        is_active=True,
    )
    account.credentials = {"api_key": "test"}
    account.save()

    with scope(organizer=organizer, event=event):
        event.settings.set("socialmedia_twitter_enabled", True)
        event.settings.set("socialmedia_cfp_enabled", True)
        event.settings.set("socialmedia_cfp_offset", "0")
        if hasattr(event, "cfp"):
            event.cfp.deadline = now() + timedelta(days=10)
            event.cfp.save()

        SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_0_twitter",
            offset_days=0,
            scheduled_at=now() + timedelta(days=1),
            post_text="CFP is open!",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    url = reverse(
        "plugins:socialmedia:preview",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["has_generated_posts"] is True
    posts = data["posts"]
    assert len(posts) >= 1

    twitter_post = [p for p in posts if p.get("platform") == "twitter"][0]
    assert twitter_post["account_handle"] == "fossasia_test"
    assert twitter_post["account_status"] == "connected"
    assert twitter_post["account_is_active"] is True


@pytest.mark.django_db
def test_bulk_discard_action(logged_in_organizer_client, organizer, event, settings):
    """Test bulk_post_action with action='discard' (Issue #62)."""
    settings.SITE_URL = "https://testserver"

    with scope(organizer=organizer, event=event):
        post1 = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_0_twitter",
            scheduled_at=now() + timedelta(days=1),
            post_text="Discard me",
            status=SocialMediaPostStatus.SCHEDULED,
        )
        post2 = SocialMediaPost.objects.create(
            event=event,
            post_type="speaker",
            entity_id="speaker_1_linkedin",
            scheduled_at=now() + timedelta(days=2),
            post_text="Keep me scheduled",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    url = reverse(
        "plugins:socialmedia:bulk_action",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload = {
        "action": "discard",
        "db_ids": [post1.pk],
    }
    response = logged_in_organizer_client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["count"] == 1

    with scope(organizer=organizer, event=event):
        post1.refresh_from_db()
        post2.refresh_from_db()
        assert post1.status == SocialMediaPostStatus.EXCLUDED
        assert post2.status == SocialMediaPostStatus.SCHEDULED


@pytest.mark.django_db
def test_bulk_retry_action(logged_in_organizer_client, organizer, event, settings):
    """Test bulk_post_action with action='retry' (Issue #64)."""
    settings.SITE_URL = "https://testserver"

    with scope(organizer=organizer, event=event):
        failed_twitter = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_0_twitter",
            scheduled_at=now() - timedelta(hours=1),
            post_text="Failed twitter post",
            status=SocialMediaPostStatus.FAILED,
            error_message="Twitter API rate limited",
        )
        failed_linkedin = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_0_linkedin",
            scheduled_at=now() - timedelta(hours=1),
            post_text="Failed linkedin post",
            status=SocialMediaPostStatus.FAILED,
            error_message="LinkedIn token expired",
        )

    url = reverse(
        "plugins:socialmedia:bulk_action",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )

    # Retry only twitter
    payload = {
        "action": "retry",
        "provider": "twitter",
    }
    response = logged_in_organizer_client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["count"] == 1

    with scope(organizer=organizer, event=event):
        failed_twitter.refresh_from_db()
        failed_linkedin.refresh_from_db()
        assert failed_twitter.status == SocialMediaPostStatus.SCHEDULED
        assert failed_twitter.error_message == ""
        # LinkedIn remains failed
        assert failed_linkedin.status == SocialMediaPostStatus.FAILED

    # Retry all remaining failed posts
    payload_all = {
        "action": "retry",
    }
    resp_all = logged_in_organizer_client.post(
        url,
        data=json.dumps(payload_all),
        content_type="application/json",
    )
    assert resp_all.status_code == 200
    assert resp_all.json()["count"] == 1

    with scope(organizer=organizer, event=event):
        failed_linkedin.refresh_from_db()
        assert failed_linkedin.status == SocialMediaPostStatus.SCHEDULED
        assert failed_linkedin.error_message == ""


@pytest.mark.django_db
def test_delayed_post_generation_and_generate_view(
    logged_in_organizer_client, organizer, event, settings
):
    """Test delayed post generation: preview returns empty unless generated, and generate endpoint creates them (Issue #65)."""
    settings.SITE_URL = "https://testserver"

    preview_url = reverse(
        "plugins:socialmedia:preview",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    # Before generation, preview returns has_generated_posts = False
    response = logged_in_organizer_client.get(preview_url)
    assert response.status_code == 200
    data = response.json()
    assert data["has_generated_posts"] is False
    assert len(data["posts"]) == 0

    # Call generate endpoint
    gen_url = reverse(
        "plugins:socialmedia:generate_posts",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    gen_response = logged_in_organizer_client.post(gen_url)
    assert gen_response.status_code == 200
    gen_data = gen_response.json()
    assert gen_data["success"] is True

    # Now preview returns generated posts
    after_response = logged_in_organizer_client.get(preview_url)
    assert after_response.status_code == 200
    after_data = after_response.json()
    assert after_data["has_generated_posts"] is True


@pytest.mark.django_db
def test_publishing_log_view_empty_and_active_state(
    logged_in_organizer_client, organizer, event, settings
):
    """Test PublishingLogView passes has_generated_posts context flag (Issue #65)."""
    settings.SITE_URL = "https://testserver"

    log_url = reverse(
        "plugins:socialmedia:log",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    # Initial state: no posts
    response = logged_in_organizer_client.get(log_url)
    assert response.status_code == 200
    assert response.context["has_generated_posts"] is False
    assert "templates_url" in response.context

    # Create a post
    with scope(organizer=organizer, event=event):
        SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_0_twitter",
            scheduled_at=now(),
            post_text="Log post",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    resp_after = logged_in_organizer_client.get(log_url)
    assert resp_after.status_code == 200
    assert resp_after.context["has_generated_posts"] is True

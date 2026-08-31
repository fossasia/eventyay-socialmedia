import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope


@pytest.mark.django_db
def test_socialmedia_settings_view_logged_out(client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:index",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = client.get(url)
    assert response.status_code == 302
    assert "login" in response.url


@pytest.mark.django_db
def test_socialmedia_settings_view_wrong_organizer(
    logged_in_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:index",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_client.get(url)
    assert response.status_code in [403, 404]


@pytest.mark.django_db
def test_socialmedia_settings_view_correct_organizer(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:index",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_socialmedia_settings_view_post(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:index",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )

    response = logged_in_organizer_client.post(
        url,
        {
            "socialmedia_default_hashtags": "#pytest #testing",
            "socialmedia_cfp_enabled": "on",
            "socialmedia_cfp_offset": "5",
            "socialmedia_cfp_template": "CFP Deadline: {cfp_deadline}",
            "socialmedia_speaker_enabled": "on",
            "socialmedia_speaker_offset": "3",
            "socialmedia_speaker_template": "Speaker: {speaker_name}",
            "socialmedia_session_enabled": "on",
            "socialmedia_session_offset": "15",
            "socialmedia_session_template": "Session: {talk_title}",
            "socialmedia_ticket_enabled": "on",
            "socialmedia_ticket_offset": "4",
            "socialmedia_ticket_template": "Ticket: {ticket_name}",
            "socialmedia_schedule_enabled": "on",
            "socialmedia_schedule_offset": "1",
            "socialmedia_schedule_template": "Schedule: {schedule_link}",
            "socialmedia_auto_publish": "on",
        },
    )

    assert response.status_code == 302

    from django.core.cache import cache

    cache.clear()

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        event.settings.flush()
        assert event.settings.get("socialmedia_default_hashtags") == "#pytest #testing"
        assert event.settings.get("socialmedia_cfp_offset") == "5"
        assert (
            event.settings.get("socialmedia_cfp_template")
            == "CFP Deadline: {cfp_deadline}"
        )
        assert event.settings.get("socialmedia_auto_publish", as_type=bool) is True


@pytest.mark.django_db
def test_update_post_view(logged_in_organizer_client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    from socialmedia.export import sync_posts_to_db
    from socialmedia.models import SocialMediaPost

    with scope(organizer=organizer, event=event):
        sync_posts_to_db(event)
        post = SocialMediaPost.objects.filter(event=event).first()
        if not post:
            post = SocialMediaPost.objects.create(
                event=event,
                post_type="custom",
                entity_id="custom_1",
                scheduled_at=event.date_from or event.created,
                post_text="Original text",
            )

    url = reverse(
        "plugins:socialmedia:update",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload = {
        "db_id": post.pk,
        "post_text": "Updated custom text",
        "post_date": "2026-07-01",
        "post_time": "14:30",
    }
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["is_pinned"] is True

    post.refresh_from_db()
    assert post.post_text == "Updated custom text"
    assert post.is_pinned is True


@pytest.mark.django_db
def test_update_post_reschedule_future_requeues_for_publishing(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    from datetime import timedelta

    import pytz
    from django.utils import timezone

    from socialmedia.models import SocialMediaPost, SocialMediaPostStatus

    event_tz = pytz.timezone(getattr(event, "timezone", None) or "UTC")
    future_dt = timezone.now().astimezone(event_tz) + timedelta(minutes=2)

    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="custom",
            entity_id="custom_reschedule_1",
            scheduled_at=timezone.now() - timedelta(days=1),
            post_text="Reschedule me",
            status=SocialMediaPostStatus.EXPORTED,
            is_pinned=False,
        )

    url = reverse(
        "plugins:socialmedia:update",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload = {
        "db_id": post.pk,
        "post_date": future_dt.strftime("%Y-%m-%d"),
        "post_time": future_dt.strftime("%H:%M"),
    }
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json()["post_status"] == SocialMediaPostStatus.SCHEDULED

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.SCHEDULED
        assert post.is_pinned is True
        assert post.error_message == ""


@pytest.mark.django_db
def test_update_post_reschedule_draft_to_future_becomes_scheduled(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    import pytz
    from django.utils import timezone
    from socialmedia.models import SocialMediaPost, SocialMediaPostStatus

    event_tz = pytz.timezone(getattr(event, "timezone", None) or "UTC")
    future_dt = timezone.now().astimezone(event_tz) + timedelta(days=2)

    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="custom",
            entity_id="custom_draft_1",
            scheduled_at=timezone.now() - timedelta(days=1),
            post_text="Draft post",
            status=SocialMediaPostStatus.DRAFT,
            is_pinned=False,
        )

    url = reverse(
        "plugins:socialmedia:update",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload = {
        "db_id": post.pk,
        "post_date": future_dt.strftime("%Y-%m-%d"),
        "post_time": future_dt.strftime("%H:%M"),
    }
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json()["post_status"] == SocialMediaPostStatus.SCHEDULED

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.SCHEDULED
        assert post.is_pinned is True


@pytest.mark.django_db
def test_preview_posts_view(logged_in_organizer_client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:preview",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert "posts" in data


@pytest.mark.django_db
def test_export_csv_view(logged_in_organizer_client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:export",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload = {
        "posts": [
            {
                "enabled": True,
                "post_date": "2026-06-20",
                "post_time": "12:00",
                "post_text": "Hello world!",
                "media_url": "",
            },
            {
                "enabled": False,
                "post_date": "2026-06-21",
                "post_time": "13:00",
                "post_text": "Skipped post",
                "media_url": "",
            },
        ]
    }
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert "attachment" in response["Content-Disposition"]

    content = response.content.decode("utf-8")
    assert "Hello world!" in content
    assert "Skipped post" not in content


@pytest.mark.django_db
def test_confirmed_submissions_and_schedule_metadata(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    try:
        from eventyay.base.models.submission import Submission, SubmissionStates
    except ImportError:
        pytest.skip("Submission model not available")

    with scope(organizer=organizer, event=event):
        try:
            from eventyay.base.models.type import SubmissionType
        except ImportError:
            from eventyay.base.models import SubmissionType

        sub_type = event.submission_types.first() or SubmissionType.objects.create(
            event=event, name="Talk"
        )
        _sub_confirmed = Submission.objects.create(
            event=event,
            submission_type=sub_type,
            title="Confirmed Session",
            state=SubmissionStates.CONFIRMED,
            code="CONF1",
        )
        _sub_accepted = Submission.objects.create(
            event=event,
            submission_type=sub_type,
            title="Accepted Only Session",
            state=SubmissionStates.ACCEPTED,
            code="ACCP1",
        )

    url = reverse(
        "plugins:socialmedia:preview",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    posts = response.json().get("posts", [])

    # Check fields in posts
    for post in posts:
        assert "event_schedule_display" in post
        assert "is_schedule_associated" in post

    session_posts = [p for p in posts if p["type"] == "session"]
    # Unscheduled submissions should NOT produce session posts — session offsets are
    # relative to talk start time in minutes, so they are meaningless without one.
    assert not any("Confirmed Session" in p["post_text"] for p in session_posts)
    assert not any("Accepted Only Session" in p["post_text"] for p in session_posts)


@pytest.mark.django_db
def test_multi_offset_generation_and_db_sync(organizer, event):
    from eventyay.base.models import Submission, SubmissionStates, User

    from socialmedia.export import build_posts, sync_posts_to_db
    from socialmedia.models import SocialMediaPost, SocialMediaPostStatus

    try:
        from eventyay.base.models.type import SubmissionType
    except ImportError:
        from eventyay.base.models import SubmissionType

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        event.date_from = now() + timedelta(days=60)
        event.save()
        sub_type = event.submission_types.first() or SubmissionType.objects.create(
            event=event, name="Talk"
        )
        sub = Submission.objects.create(
            event=event,
            submission_type=sub_type,
            title="Multi Offset Talk",
            state=SubmissionStates.CONFIRMED,
            code="MOFF1",
        )
        speaker = User.objects.create(fullname="Jane Doe", email="jane@example.com")
        sub.speakers.add(speaker)

        event.settings.set("socialmedia_speaker_offset", "30, 7, 1")
        event.settings.flush()

        posts = build_posts(event)
        speaker_posts = [p for p in posts if p["type"] == "speaker"]
        assert len(speaker_posts) == 3

        sync_posts_to_db(event)
        db_posts = SocialMediaPost.objects.filter(event=event, post_type="speaker")
        assert db_posts.count() == 3
        assert all(p.status == SocialMediaPostStatus.SCHEDULED for p in db_posts)


@pytest.mark.django_db
def test_sync_posts_to_db_past_draft_future_scheduled(organizer, event):
    from socialmedia.export import build_posts, sync_posts_to_db
    from socialmedia.models import SocialMediaPost, SocialMediaPostStatus

    with scope(organizer=organizer, event=event):
        # Event in the past
        event = event.__class__.objects.get(pk=event.pk)
        event.date_from = now() - timedelta(days=60)
        event.save()

        posts = build_posts(event)
        if posts:
            sync_posts_to_db(event)
            past_posts = SocialMediaPost.objects.filter(event=event)
            assert all(p.status == SocialMediaPostStatus.DRAFT for p in past_posts)

        # Event in the future
        event.date_from = now() + timedelta(days=60)
        event.save()
        sync_posts_to_db(event)
        future_posts = SocialMediaPost.objects.filter(event=event)
        assert any(p.status == SocialMediaPostStatus.SCHEDULED for p in future_posts)


@pytest.mark.django_db
def test_post_exclusion_from_preview(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    import json

    from socialmedia.export import sync_posts_to_db
    from socialmedia.models import SocialMediaPost

    # 1. Sync posts and get one
    with scope(organizer=organizer, event=event):
        sync_posts_to_db(event)
        post = SocialMediaPost.objects.filter(event=event).first()
        if not post:
            post = SocialMediaPost.objects.create(
                event=event,
                post_type="custom",
                entity_id="custom_excl_1",
                scheduled_at=event.date_from or event.created,
                post_text="Test exclusion post",
            )

    # 2. Assert it is present in preview
    url_preview = reverse(
        "plugins:socialmedia:preview",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url_preview)
    assert response.status_code == 200
    posts = response.json().get("posts", [])
    assert any(
        p.get("id") == post.entity_id or p.get("db_id") == post.pk for p in posts
    )

    # 3. Update status to excluded
    url_update = reverse(
        "plugins:socialmedia:update",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload = {
        "db_id": post.pk,
        "status": "excluded",
    }
    response_update = logged_in_organizer_client.post(
        url_update, data=json.dumps(payload), content_type="application/json"
    )
    assert response_update.status_code == 200
    assert response_update.json()["status"] == "ok"

    # 4. Assert it is returned with status "excluded"
    response_after = logged_in_organizer_client.get(url_preview)
    posts_after = response_after.json().get("posts", [])
    matched_post = next(
        (
            p
            for p in posts_after
            if p.get("id") == post.entity_id or p.get("db_id") == post.pk
        ),
        None,
    )
    assert matched_post is not None
    assert matched_post.get("status") == "excluded"


# ---------------------------------------------------------------------------
# Multi-platform tests (Issue #21)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_multi_platform_build_posts(organizer, event):
    """Enabling 2 platforms should double the number of posts generated, and
    every post should have a 'platform' field matching one of the enabled ones."""
    from django_scopes import scope

    from socialmedia.export import build_posts

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        event.settings.set("socialmedia_twitter_enabled", True)
        event.settings.set("socialmedia_linkedin_enabled", True)
        # Ensure at least one content type is enabled so posts are generated
        event.settings.set("socialmedia_schedule_enabled", True)
        event.settings.flush()

        posts_without_platforms = []
        # Temporarily collect the count without platforms
        event.settings.set("socialmedia_twitter_enabled", False)
        event.settings.set("socialmedia_linkedin_enabled", False)
        event.settings.flush()
        posts_without_platforms = build_posts(event)

        event.settings.set("socialmedia_twitter_enabled", True)
        event.settings.set("socialmedia_linkedin_enabled", True)
        event.settings.flush()
        posts_with_platforms = build_posts(event)

    # Posts with 2 platforms should be 2× the generic count (if any generic exist)
    if posts_without_platforms:
        assert len(posts_with_platforms) == len(posts_without_platforms) * 2

    # Every post must have a 'platform' key set to one of the enabled platforms
    for post in posts_with_platforms:
        assert "platform" in post
        assert post["platform"] in ("twitter", "linkedin")


@pytest.mark.django_db
def test_platform_uses_correct_template(organizer, event):
    """A platform-specific saved template should appear in the generated post text."""
    from django_scopes import scope

    from socialmedia.export import build_posts

    custom_tpl = "CUSTOM_TWITTER_SCHEDULE: {schedule_link}"

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        event.settings.set("socialmedia_twitter_enabled", True)
        event.settings.set("socialmedia_schedule_enabled", True)
        event.settings.set("socialmedia_twitter_schedule_template", custom_tpl)
        event.settings.flush()

        posts = build_posts(event)

    twitter_schedule_posts = [
        p for p in posts if p["type"] == "schedule" and p.get("platform") == "twitter"
    ]
    assert twitter_schedule_posts, "Expected at least one Twitter schedule post"
    assert all(
        "CUSTOM_TWITTER_SCHEDULE" in p["post_text"] for p in twitter_schedule_posts
    )


@pytest.mark.django_db
def test_no_platforms_fallback(organizer, event):
    """When no platforms are enabled, posts should have no platform key (or None)
    — preserving full backwards compatibility."""
    from django_scopes import scope

    from socialmedia.export import build_posts

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        for plat in ("twitter", "mastodon", "telegram", "linkedin"):
            event.settings.set(f"socialmedia_{plat}_enabled", False)
        event.settings.set("socialmedia_schedule_enabled", True)
        event.settings.flush()

        posts = build_posts(event)

    for post in posts:
        assert (
            post.get("platform") is None
        ), f"Expected no platform on post {post['id']}, got {post['platform']!r}"


@pytest.mark.django_db
def test_export_csv_presets(logged_in_organizer_client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:socialmedia:export",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    payload_base = {
        "posts": [
            {
                "enabled": True,
                "post_date": "2026-06-20",
                "post_time": "12:00",
                "post_text": "Hello world!",
                "media_url": "https://testserver/img.png",
            }
        ]
    }

    # Test Postiz preset
    payload = payload_base.copy()
    payload["format"] = "postiz"
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "content,date,time,media" in content
    assert "Hello world!,2026-06-20,12:00,https://testserver/img.png" in content

    # Test Buffer preset
    payload = payload_base.copy()
    payload["format"] = "buffer"
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "text,scheduled_at,link,image" in content
    assert "Hello world!,2026-06-20 12:00,,https://testserver/img.png" in content

    # Test Hootsuite preset
    payload = payload_base.copy()
    payload["format"] = "hootsuite"
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "date,time,text,link" in content
    assert "2026-06-20,12:00,Hello world!,https://testserver/img.png" in content


@pytest.mark.django_db
def test_build_posts_includes_speaker_avatar(organizer, event):
    from unittest.mock import patch

    from django_scopes import scope
    from eventyay.base.models.auth import User
    from eventyay.base.models.submission import Submission

    try:
        from eventyay.base.models.type import SubmissionType
    except ImportError:
        from eventyay.base.models import SubmissionType
    from socialmedia.export import build_posts

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        event.settings.set("socialmedia_speaker_enabled", True)
        event.settings.flush()

        sub_type = event.submission_types.first() or SubmissionType.objects.create(
            event=event, name="Talk"
        )

        user = User.objects.create_user("speaker@example.com", "password")

        sub = Submission.objects.create(
            event=event,
            submission_type=sub_type,
            title="Awesome Talk",
            state="confirmed",
        )
        sub.speakers.add(user)

        with patch.object(
            User, "get_avatar_url", return_value="https://testserver/speaker.jpg"
        ):
            posts = build_posts(event)

    speaker_posts = [p for p in posts if p["type"] == "speaker"]
    assert speaker_posts
    assert speaker_posts[0]["media_url"] == "https://testserver/speaker.jpg"


@pytest.mark.django_db
def test_sync_posts_to_db_saves_media_url(organizer, event):
    from unittest.mock import patch

    from django_scopes import scope
    from eventyay.base.models.auth import User
    from eventyay.base.models.submission import Submission

    try:
        from eventyay.base.models.type import SubmissionType
    except ImportError:
        from eventyay.base.models import SubmissionType
    from socialmedia.export import sync_posts_to_db
    from socialmedia.models import SocialMediaPost

    with scope(organizer=organizer, event=event):
        event = event.__class__.objects.get(pk=event.pk)
        event.settings.set("socialmedia_speaker_enabled", True)
        event.settings.flush()

        sub_type = event.submission_types.first() or SubmissionType.objects.create(
            event=event, name="Talk"
        )

        user = User.objects.create_user("speaker2@example.com", "password")

        sub = Submission.objects.create(
            event=event,
            submission_type=sub_type,
            title="Another Talk",
            state="confirmed",
        )
        sub.speakers.add(user)

        with patch(
            "socialmedia.export.build_posts",
            return_value=[
                {
                    "id": sub.pk,
                    "type": "speaker",
                    "post_date": "2026-07-28",
                    "post_time": "12:00",
                    "post_text": "Talk by speaker2",
                    "offset_days": 0,
                    "media_url": "https://testserver/speaker.jpg",
                }
            ],
        ):
            sync_posts_to_db(event)

        db_posts = SocialMediaPost.objects.filter(event=event, post_type="speaker")
        assert db_posts.exists()

        post = db_posts.first()
        assert post.media_url == "https://testserver/speaker.jpg"
        with patch(
            "socialmedia.export.build_posts",
            return_value=[
                {
                    "id": sub.pk,
                    "type": "speaker",
                    "post_date": "2026-07-28",
                    "post_time": "12:00",
                    "post_text": "Talk by speaker2",
                    "offset_days": 0,
                    "media_url": "https://testserver/speaker.jpg",
                }
            ],
        ):
            sync_posts_to_db(event)

        db_posts = SocialMediaPost.objects.filter(event=event, post_type="speaker")
        assert db_posts.exists()

        post = db_posts.first()
        assert post.media_url == "https://testserver/speaker.jpg"

        # Verify re-syncing preserves existing media_url if payload omits it
        with patch(
            "socialmedia.export.build_posts",
            return_value=[
                {
                    "id": sub.pk,
                    "type": "speaker",
                    "post_date": "2026-07-28",
                    "post_time": "12:00",
                    "post_text": "Updated Text",
                    "offset_days": 0,
                }
            ],
        ):
            sync_posts_to_db(event)

        post.refresh_from_db()
        assert post.media_url == "https://testserver/speaker.jpg"


@pytest.mark.django_db
def test_post_error_message_persistence(organizer, event):
    from django.utils.timezone import now
    from django_scopes import scope

    from socialmedia.models import SocialMediaPost

    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="general",
            scheduled_at=now(),
            post_text="Test Post",
            status="failed",
            error_message="API Connection Timeout",
        )
        post.refresh_from_db()
        assert post.error_message == "API Connection Timeout"





@pytest.mark.django_db
def test_publish_post_now_view(logged_in_organizer_client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    from unittest.mock import patch

    from django.utils.timezone import now
    from django_scopes import scope

    from socialmedia.models import (
        SocialMediaAccount,
        SocialMediaPost,
        SocialMediaPostStatus,
    )
    from socialmedia.providers.telegram import TelegramProvider

    url = reverse(
        "plugins:socialmedia:publish_now",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )

    with scope(organizer=organizer, event=event):
        post = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_1_telegram",
            scheduled_at=now(),
            post_text="Publish now!",
            status=SocialMediaPostStatus.SCHEDULED,
        )

    payload = {"db_id": post.pk}
    response = logged_in_organizer_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert "No active telegram account found" in response.json()["message"]

    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="telegram",
        platform_username="telegram_chan",
        is_active=True,
    )
    account.credentials = {"bot_token": "fake"}
    account.save()

    with patch.object(TelegramProvider, "publish_post") as mock_publish:
        response = logged_in_organizer_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        assert response.status_code == 200
        assert "successfully published" in response.json()["message"].lower()
        mock_publish.assert_called_once_with(text="Publish now!", media=None)

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.PUBLISHED

    post.status = SocialMediaPostStatus.SCHEDULED
    with scope(organizer=organizer, event=event):
        post.save()

    from socialmedia.providers.base import PublishingError

    with patch.object(
        TelegramProvider, "publish_post", side_effect=PublishingError("Rate limited")
    ) as mock_publish:
        response = logged_in_organizer_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        assert response.status_code == 500
        assert "Publishing failed:" in response.json()["message"]
        assert "Rate limited" in response.json()["message"]

    with scope(organizer=organizer, event=event):
        post.refresh_from_db()
        assert post.status == SocialMediaPostStatus.FAILED
        assert "Rate limited" in post.error_message

        legacy_post = SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_1_postiz",
            scheduled_at=now(),
            post_text="Legacy post",
            status=SocialMediaPostStatus.SCHEDULED,
        )
    resp_legacy = logged_in_organizer_client.post(
        url, data=json.dumps({"db_id": legacy_post.pk}), content_type="application/json"
    )
    assert resp_legacy.status_code == 400
    assert "legacy scheduler integration" in resp_legacy.json()["message"]

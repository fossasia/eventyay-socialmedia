import json

import pytest
from django.urls import reverse
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
    # Should include confirmed session but not accepted session
    titles = [p["post_text"] for p in session_posts]
    assert any("Confirmed Session" in t for t in titles)
    assert not any("Accepted Only Session" in t for t in titles)

    # Check unscheduled status
    conf_post = next(p for p in session_posts if "Confirmed Session" in p["post_text"])
    assert conf_post["event_schedule_display"] == "Unscheduled"
    assert conf_post["is_schedule_associated"] is True


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

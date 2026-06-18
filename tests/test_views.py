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

    with scope(organizer=organizer):
        event.settings.flush()
        assert event.settings.get("socialmedia_default_hashtags") == "#pytest #testing"
        assert event.settings.get("socialmedia_cfp_offset") == "5"
        assert (
            event.settings.get("socialmedia_cfp_template")
            == "CFP Deadline: {cfp_deadline}"
        )


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

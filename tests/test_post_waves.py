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
from socialmedia.providers.telegram import TelegramProvider

# The reminder wave, which is saved after the announcement wave of the same post.
REMINDER = {"post_type": "cfp", "offset_days": 10}


@pytest.fixture
def waves(organizer, event, settings):
    """Two waves of the same CfP post: an announcement and a reminder."""
    settings.SITE_URL = "https://testserver"
    with scope(organizer=organizer, event=event):
        return {
            offset: SocialMediaPost.objects.create(
                event=event,
                post_type="cfp",
                entity_id="cfp_0_telegram",
                offset_days=offset,
                scheduled_at=now() + timedelta(days=1),
                post_text=text,
                status=SocialMediaPostStatus.SCHEDULED,
            )
            for offset, text in ((45, "The CfP is open!"), (10, "Ten days left!"))
        }


def post_json(client, organizer, event, name, payload):
    url = reverse(
        f"plugins:socialmedia:{name}",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def reload(organizer, event, waves):
    with scope(organizer=organizer, event=event):
        for post in waves.values():
            post.refresh_from_db()


@pytest.mark.django_db
def test_bulk_discard_only_discards_the_selected_wave(
    logged_in_organizer_client, organizer, event, waves
):
    payload = {"action": "discard", "posts": [{"id": "cfp_0_telegram", **REMINDER}]}
    response = post_json(
        logged_in_organizer_client, organizer, event, "bulk_action", payload
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    reload(organizer, event, waves)
    assert waves[10].status == SocialMediaPostStatus.EXCLUDED
    assert waves[45].status == SocialMediaPostStatus.SCHEDULED


@pytest.mark.django_db
def test_editing_a_wave_without_db_id_changes_only_that_wave(
    logged_in_organizer_client, organizer, event, waves
):
    payload = {"id": "cfp_0_telegram", **REMINDER, "post_text": "Last call!"}
    response = post_json(
        logged_in_organizer_client, organizer, event, "update", payload
    )

    assert response.status_code == 200
    assert response.json()["db_id"] == waves[10].pk
    reload(organizer, event, waves)
    assert waves[10].post_text == "Last call!"
    assert waves[45].post_text == "The CfP is open!"


@pytest.mark.django_db
def test_changing_the_status_of_a_wave_without_db_id_changes_only_that_wave(
    logged_in_organizer_client, organizer, event, waves
):
    payload = {"id": "cfp_0_telegram", **REMINDER, "status": "excluded"}
    response = post_json(
        logged_in_organizer_client, organizer, event, "update", payload
    )

    assert response.status_code == 200
    reload(organizer, event, waves)
    assert waves[10].status == SocialMediaPostStatus.EXCLUDED
    assert waves[45].status == SocialMediaPostStatus.SCHEDULED


@pytest.mark.django_db
def test_publishing_a_wave_without_db_id_publishes_only_that_wave(
    logged_in_organizer_client, organizer, event, waves
):
    account = SocialMediaAccount.objects.create(
        organizer=organizer,
        provider="telegram",
        platform_username="telegram_chan",
        is_active=True,
    )
    account.credentials = {"bot_token": "fake"}
    account.save()

    with patch.object(TelegramProvider, "publish_post") as publish:
        payload = {"post_id": "cfp_0_telegram", **REMINDER}
        response = post_json(
            logged_in_organizer_client, organizer, event, "publish_now", payload
        )

    assert response.status_code == 200
    publish.assert_called_once_with(text="Ten days left!", media=None)
    reload(organizer, event, waves)
    assert waves[10].status == SocialMediaPostStatus.PUBLISHED
    assert waves[45].status == SocialMediaPostStatus.SCHEDULED

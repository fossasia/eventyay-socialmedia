from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone
from django_scopes import scope
from eventyay.base.models import Organizer, Team

from socialmedia.models import (
    SocialMediaAccount,
    SocialMediaPost,
    SocialMediaPostStatus,
)
from socialmedia.signals import control_nav_organizer_socialmedia


@pytest.fixture
def organizer_admin_client(logged_in_organizer_client, organizer, settings):
    # Grant organizer settings permission to the test team
    with scope(organizer=organizer):
        team = Team.objects.filter(organizer=organizer).first()
        if team:
            team.can_change_organizer_settings = True
            team.save()
    settings.SITE_URL = "https://testserver"
    return logged_in_organizer_client


@pytest.mark.django_db
def test_nav_organizer_signal_no_permission(organizer, user):
    class MockRequest:
        def __init__(self):
            self.user = user
            self.path_info = "/control/"
            self.session = MagicMock()

    request = MockRequest()
    # User has no permissions
    items = control_nav_organizer_socialmedia(organizer, request=request)
    assert items == []


@pytest.mark.django_db
def test_nav_organizer_signal_with_permission(organizer, user):
    team = Team.objects.create(
        organizer=organizer,
        name="Test Admin Team",
        can_change_organizer_settings=True,
        all_events=True,
    )
    team.members.add(user)

    class StubResolverMatch:
        url_name = "organizer_accounts"
        namespace = "plugins:socialmedia"

    class MockRequest:
        def __init__(self):
            self.user = user
            self.path_info = f"/social/organizer/{organizer.slug}/accounts/"
            self.resolver_match = StubResolverMatch()
            self.session = MagicMock()

    request = MockRequest()
    items = control_nav_organizer_socialmedia(organizer, request=request)
    assert len(items) == 1
    assert items[0]["label"] == "Social Media Accounts"
    assert items[0]["url"] == reverse(
        "plugins:socialmedia:organizer_accounts",
        kwargs={"organizer": organizer.slug},
    )


@pytest.mark.django_db
def test_accounts_list_view(organizer_admin_client, organizer):
    with scope(organizer=organizer):
        SocialMediaAccount.objects.create(
            organizer=organizer,
            provider="telegram",
            platform_username="@mychannel",
            encrypted_credentials="{}",
        )

    url = reverse(
        "plugins:socialmedia:organizer_accounts",
        kwargs={"organizer": organizer.slug},
    )
    response = organizer_admin_client.get(url)
    assert response.status_code == 200
    assert "@mychannel" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_account_create_view_no_provider(organizer_admin_client, organizer):
    url = reverse(
        "plugins:socialmedia:organizer_account_add",
        kwargs={"organizer": organizer.slug},
    )
    response = organizer_admin_client.get(url)
    # Should redirect to list view if no provider specified
    assert response.status_code == 302
    assert "accounts" in response.url


@pytest.mark.django_db
def test_account_create_view_valid_provider(organizer_admin_client, organizer):
    url = (
        reverse(
            "plugins:socialmedia:organizer_account_add",
            kwargs={"organizer": organizer.slug},
        )
        + "?provider=telegram"
    )
    response = organizer_admin_client.get(url)
    assert response.status_code == 200
    assert "Bot API Token" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_account_create_post(organizer_admin_client, organizer):
    url = (
        reverse(
            "plugins:socialmedia:organizer_account_add",
            kwargs={"organizer": organizer.slug},
        )
        + "?provider=telegram"
    )

    payload = {
        "platform_username": "@testchannel",
        "bot_token": "my_secret_bot_token",
        "is_active": "on",
    }
    response = organizer_admin_client.post(url, data=payload)
    assert response.status_code == 302

    with scope(organizer=organizer):
        account = SocialMediaAccount.objects.get(platform_username="@testchannel")
        assert account.provider == "telegram"
        assert account.credentials == {"bot_token": "my_secret_bot_token"}
        assert account.is_active is True


@pytest.mark.django_db
def test_account_update_view(organizer_admin_client, organizer):
    with scope(organizer=organizer):
        account = SocialMediaAccount.objects.create(
            organizer=organizer,
            provider="telegram",
            platform_username="@testchannel",
        )
        account.credentials = {"bot_token": "old_token"}
        account.save()

    url = reverse(
        "plugins:socialmedia:organizer_account_edit",
        kwargs={"organizer": organizer.slug, "pk": account.pk},
    )
    response = organizer_admin_client.get(url)
    assert response.status_code == 200
    # Should render password input with placeholder
    assert "••••••••" in response.content.decode("utf-8")

    # POST with blank secret - should keep old token
    payload = {
        "platform_username": "@newchannel",
        "bot_token": "",
        "is_active": "on",
    }
    response = organizer_admin_client.post(url, data=payload)
    assert response.status_code == 302

    account.refresh_from_db()
    assert account.platform_username == "@newchannel"
    assert account.credentials == {"bot_token": "old_token"}


@pytest.mark.django_db
def test_account_delete_view_without_active_posts(organizer_admin_client, organizer):
    with scope(organizer=organizer):
        account = SocialMediaAccount.objects.create(
            organizer=organizer,
            provider="telegram",
            platform_username="@testchannel",
        )

    url = reverse(
        "plugins:socialmedia:organizer_account_delete",
        kwargs={"organizer": organizer.slug, "pk": account.pk},
    )
    response = organizer_admin_client.get(url)
    assert response.status_code == 200
    assert "Warning: Active Scheduled Posts" not in response.content.decode()

    # POST to delete
    response = organizer_admin_client.post(url)
    assert response.status_code == 302
    with scope(organizer=organizer):
        assert not SocialMediaAccount.objects.filter(pk=account.pk).exists()


@pytest.mark.django_db
def test_account_delete_view_with_active_posts(
    organizer_admin_client, organizer, event
):
    with scope(organizer=organizer):
        account = SocialMediaAccount.objects.create(
            organizer=organizer,
            provider="telegram",
            platform_username="@testchannel",
        )

    with scope(organizer=organizer, event=event):
        SocialMediaPost.objects.create(
            event=event,
            post_type="cfp",
            entity_id="cfp_telegram",
            scheduled_at=timezone.now() + timedelta(days=1),
            status=SocialMediaPostStatus.SCHEDULED,
            post_text="Test",
        )

    url = reverse(
        "plugins:socialmedia:organizer_account_delete",
        kwargs={"organizer": organizer.slug, "pk": account.pk},
    )
    response = organizer_admin_client.get(url)
    assert response.status_code == 200
    # Should display the warnings warning
    assert "Warning: Active Scheduled Posts" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_multi_tenancy_isolation(organizer_admin_client, organizer, settings):
    # Create another organizer
    other_org = Organizer.objects.create(name="Other Organizer", slug="other-org")
    with scope(organizer=other_org):
        other_account = SocialMediaAccount.objects.create(
            organizer=other_org,
            provider="telegram",
            platform_username="@otherchannel",
        )

    url = reverse(
        "plugins:socialmedia:organizer_account_edit",
        kwargs={"organizer": organizer.slug, "pk": other_account.pk},
    )
    # Trying to access other organizer's connection via our organizer slug
    response = organizer_admin_client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
@patch("socialmedia.providers.telegram.TelegramProvider.send_test_message")
def test_test_connection_view(mock_send_test, organizer_admin_client, organizer):
    mock_send_test.return_value = {"success": True, "message": "Test message sent."}
    with scope(organizer=organizer):
        account = SocialMediaAccount.objects.create(
            organizer=organizer,
            provider="telegram",
            platform_username="@mychannel",
            credentials={"bot_token": "fake_token"},
        )

    url = reverse(
        "plugins:socialmedia:organizer_account_test",
        kwargs={"organizer": organizer.slug, "pk": account.pk},
    )
    response = organizer_admin_client.post(url, content_type="application/json")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Test message sent."

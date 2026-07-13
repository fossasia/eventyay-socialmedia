from unittest.mock import MagicMock, mock_open, patch

import pytest

from socialmedia.models import SocialMediaAccount
from socialmedia.providers import (
    BaseSocialProvider,
    PublishingError,
    get_provider,
    get_provider_class,
)
from socialmedia.providers.buffer import BufferProvider
from socialmedia.providers.mastodon import MastodonProvider
from socialmedia.providers.postiz import PostizProvider
from socialmedia.providers.telegram import TelegramProvider


@pytest.fixture
def mock_account():
    account = MagicMock(spec=SocialMediaAccount)
    account.provider = "telegram"
    account.platform_username = "@testchannel"
    account.credentials = {"bot_token": "fake_token"}
    return account


def test_base_provider_raises_not_implemented(mock_account):
    provider = BaseSocialProvider(mock_account)
    with pytest.raises(NotImplementedError):
        provider.validate_credentials()
    with pytest.raises(NotImplementedError):
        provider.publish_post("text")
    assert provider.sync_campaign([]) == []


def test_registry_get_provider_class():
    assert get_provider_class("telegram") == TelegramProvider
    assert get_provider_class("mastodon") == MastodonProvider
    assert get_provider_class("postiz") == PostizProvider
    assert get_provider_class("buffer") == BufferProvider
    with pytest.raises(ValueError):
        get_provider_class("unknown")


def test_registry_get_provider(mock_account):
    provider = get_provider(mock_account)
    assert isinstance(provider, TelegramProvider)


@patch("requests.get")
def test_telegram_validate_credentials(mock_get, mock_account):
    provider = TelegramProvider(mock_account)

    # Valid credentials
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}
    mock_get.return_value = mock_response
    assert provider.validate_credentials() is True

    # Invalid credentials
    mock_response.json.return_value = {"ok": False}
    assert provider.validate_credentials() is False

    # HTTP error
    mock_get.side_effect = Exception("HTTP Error")
    assert provider.validate_credentials() is False


@patch("requests.post")
def test_telegram_publish_post_text_only(mock_post, mock_account):
    provider = TelegramProvider(mock_account)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}
    mock_post.return_value = mock_response

    res = provider.publish_post("hello world")
    assert res["post_id"] == "123"
    assert res["url"] == "https://t.me/testchannel/123"
    mock_post.assert_called_once()


@patch("builtins.open", new_callable=mock_open, read_data=b"image_data")
@patch("requests.post")
def test_telegram_publish_post_with_local_media(mock_post, mock_file, mock_account):
    provider = TelegramProvider(mock_account)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 456}}
    mock_post.return_value = mock_response

    res = provider.publish_post("hello with media", media=["/path/to/img.png"])
    assert res["post_id"] == "456"
    assert "sendPhoto" in mock_post.call_args[0][0]


@patch("requests.post")
def test_telegram_publish_post_with_remote_media(mock_post, mock_account):
    provider = TelegramProvider(mock_account)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 789}}
    mock_post.return_value = mock_response

    res = provider.publish_post(
        "hello remote media", media=["https://example.com/img.png"]
    )
    assert res["post_id"] == "789"
    assert "photo" in mock_post.call_args[1]["data"]


@patch("requests.post")
def test_telegram_publish_error(mock_post, mock_account):
    provider = TelegramProvider(mock_account)
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    mock_post.return_value = mock_response

    with pytest.raises(PublishingError):
        provider.publish_post("hello error")


@patch("socialmedia.providers.mastodon.Mastodon")
def test_mastodon_validate_credentials(mock_mastodon_cls, mock_account):
    mock_account.provider = "mastodon"
    mock_account.credentials = {
        "api_base_url": "https://mastodon.social",
        "access_token": "fake_token",
    }
    provider = MastodonProvider(mock_account)

    # Valid credentials
    mock_client = mock_mastodon_cls.return_value
    mock_client.account_verify_credentials.return_value = {"username": "testuser"}
    assert provider.validate_credentials() is True

    # Invalid credentials
    mock_client.account_verify_credentials.side_effect = Exception("Invalid token")
    assert provider.validate_credentials() is False


@patch("socialmedia.providers.mastodon.Mastodon")
def test_mastodon_publish_post(mock_mastodon_cls, mock_account):
    mock_account.provider = "mastodon"
    mock_account.credentials = {
        "api_base_url": "https://mastodon.social",
        "access_token": "fake_token",
    }
    provider = MastodonProvider(mock_account)
    mock_client = mock_mastodon_cls.return_value
    mock_client.status_post.return_value = {
        "id": 12345,
        "url": "https://mastodon.social/@testuser/12345",
    }

    res = provider.publish_post("Mastodon post")
    assert res["post_id"] == "12345"
    assert res["url"] == "https://mastodon.social/@testuser/12345"


@patch("requests.get")
def test_postiz_validate_credentials(mock_get, mock_account):
    mock_account.provider = "postiz"
    mock_account.credentials = {
        "api_url": "https://api.postiz.com",
        "api_key": "fake_key",
    }
    provider = PostizProvider(mock_account)

    # Valid
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    assert provider.validate_credentials() is True

    # Invalid
    mock_response.status_code = 401
    assert provider.validate_credentials() is False


@patch("requests.post")
def test_postiz_publish_post(mock_post, mock_account):
    mock_account.provider = "postiz"
    mock_account.credentials = {
        "api_url": "https://api.postiz.com",
        "api_key": "fake_key",
    }
    provider = PostizProvider(mock_account)
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "id": "postiz_123",
        "url": "https://postiz.com/posts/postiz_123",
    }
    mock_post.return_value = mock_response

    res = provider.publish_post("Postiz status")
    assert res["post_id"] == "postiz_123"
    assert res["url"] == "https://postiz.com/posts/postiz_123"


@patch("requests.get")
def test_buffer_validate_credentials(mock_get, mock_account):
    mock_account.provider = "buffer"
    mock_account.credentials = {
        "access_token": "fake_token",
    }
    provider = BufferProvider(mock_account)

    # Valid
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    assert provider.validate_credentials() is True

    # Invalid
    mock_response.status_code = 403
    assert provider.validate_credentials() is False


@patch("requests.post")
def test_buffer_publish_post(mock_post, mock_account):
    mock_account.provider = "buffer"
    mock_account.platform_username = "profile123"
    mock_account.credentials = {
        "access_token": "fake_token",
    }
    provider = BufferProvider(mock_account)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"updates": [{"id": "buffer_123"}]}
    mock_post.return_value = mock_response

    res = provider.publish_post("Buffer update")
    assert res["post_id"] == "buffer_123"
    assert "profile_ids[]" in mock_post.call_args[1]["data"]

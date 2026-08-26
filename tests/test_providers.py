from unittest.mock import MagicMock, mock_open, patch

import pytest

from socialmedia.models import SocialMediaAccount
from socialmedia.providers import (
    BaseSocialProvider,
    PublishingError,
    get_provider,
    get_provider_class,
)
from socialmedia.providers.linkedin import LinkedInProvider
from socialmedia.providers.mastodon import MastodonProvider
from socialmedia.providers.telegram import TelegramProvider
from socialmedia.providers.twitter import TwitterProvider


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


def test_registry_get_provider_class():
    assert get_provider_class("telegram") == TelegramProvider
    assert get_provider_class("mastodon") == MastodonProvider
    assert get_provider_class("twitter") == TwitterProvider
    assert get_provider_class("linkedin") == LinkedInProvider
    with pytest.raises(ValueError):
        get_provider_class("postiz")
    with pytest.raises(ValueError):
        get_provider_class("buffer")
    with pytest.raises(ValueError):
        get_provider_class("unknown")


def test_registry_get_provider(mock_account):
    provider = get_provider(mock_account)
    assert isinstance(provider, TelegramProvider)


def test_telegram_provider_normalizes_web_telegram_url(mock_account):
    mock_account.platform_username = "https://web.telegram.org/k/#-4482182411"
    provider = TelegramProvider(mock_account)

    assert provider.chat_id == "-1004482182411"
    assert provider._resolve_chat_id() == -1004482182411


@patch("requests.get")
def test_telegram_validate_credentials(mock_get, mock_account):
    provider = TelegramProvider(mock_account)

    # Valid credentials
    mock_get_me_response = MagicMock()
    mock_get_me_response.status_code = 200
    mock_get_me_response.json.return_value = {"ok": True}
    mock_get_chat_response = MagicMock()
    mock_get_chat_response.status_code = 200
    mock_get_chat_response.json.return_value = {"ok": True}
    mock_get.side_effect = [mock_get_me_response, mock_get_chat_response]
    assert provider.validate_credentials() is True

    # Invalid credentials
    mock_get.reset_mock(side_effect=True)
    mock_get_me_response.json.return_value = {"ok": False}
    mock_get.return_value = mock_get_me_response
    assert provider.validate_credentials() is False

    # HTTP error
    mock_get.side_effect = Exception("HTTP Error")
    assert provider.validate_credentials() is False


@patch("requests.get")
def test_telegram_validate_credentials_checks_chat(mock_get, mock_account):
    provider = TelegramProvider(mock_account)
    mock_get_me_response = MagicMock()
    mock_get_me_response.status_code = 200
    mock_get_me_response.json.return_value = {"ok": True}
    mock_get_chat_response = MagicMock()
    mock_get_chat_response.status_code = 400
    mock_get_chat_response.json.return_value = {
        "ok": False,
        "description": "Bad Request: chat not found",
    }
    mock_get.side_effect = [mock_get_me_response, mock_get_chat_response]

    assert provider.validate_credentials() is False
    assert mock_get.call_args_list[1].kwargs["params"] == {"chat_id": "@testchannel"}


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


@patch("builtins.open", new_callable=mock_open, read_data=b"image_data")
@patch("requests.post")
def test_telegram_publish_post_local_media_markdown_retry(
    mock_post, mock_file, mock_account
):
    provider = TelegramProvider(mock_account)
    err_response = MagicMock()
    err_response.status_code = 400
    err_response.text = "Bad Request: can't parse entities"

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {"ok": True, "result": {"message_id": 999}}

    mock_post.side_effect = [err_response, ok_response]

    res = provider.publish_post("hello *bad markdown*", media=["/path/to/img.png"])
    assert res["post_id"] == "999"
    assert mock_post.call_count == 2
    retry_call = mock_post.call_args_list[1]
    assert "files" in retry_call[1]
    assert "parse_mode" not in retry_call[1]["data"]


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
def test_twitter_validate_credentials(mock_get, mock_account):
    mock_account.provider = "twitter"
    mock_account.credentials = {
        "api_key": "k",
        "api_secret": "s",
        "access_token": "at",
        "access_token_secret": "ats",
    }
    provider = TwitterProvider(mock_account)

    # Success
    res_ok = MagicMock()
    res_ok.status_code = 200
    mock_get.return_value = res_ok
    assert provider.validate_credentials() is True

    # Error
    res_err = MagicMock()
    res_err.status_code = 401
    res_err.json.return_value = {"detail": "Unauthorized"}
    mock_get.return_value = res_err
    with pytest.raises(PublishingError):
        provider.validate_credentials()


@patch("requests.post")
def test_twitter_publish_post(mock_post, mock_account):
    mock_account.provider = "twitter"
    mock_account.platform_username = "@eventyay"
    mock_account.credentials = {
        "api_key": "k",
        "api_secret": "s",
        "access_token": "at",
        "access_token_secret": "ats",
    }
    provider = TwitterProvider(mock_account)

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"data": {"id": "tweet_12345"}}
    mock_post.return_value = mock_resp

    res = provider.publish_post("Hello Twitter")
    assert res["post_id"] == "tweet_12345"
    assert res["url"] == "https://x.com/eventyay/status/tweet_12345"


@patch("requests.get")
def test_linkedin_validate_credentials(mock_get, mock_account):
    mock_account.provider = "linkedin"
    mock_account.credentials = {
        "access_token": "fake_li_token",
        "author_urn": "urn:li:person:12345",
    }
    provider = LinkedInProvider(mock_account)

    res_ok = MagicMock()
    res_ok.status_code = 200
    mock_get.return_value = res_ok
    assert provider.validate_credentials() is True

    res_err = MagicMock()
    res_err.status_code = 401
    res_err.json.return_value = {"message": "Invalid token"}
    mock_get.return_value = res_err
    with pytest.raises(PublishingError):
        provider.validate_credentials()


@patch("requests.post")
def test_linkedin_publish_post(mock_post, mock_account):
    mock_account.provider = "linkedin"
    mock_account.platform_username = "Eventyay Page"
    mock_account.credentials = {
        "access_token": "fake_li_token",
        "author_urn": "urn:li:organization:98765",
    }
    provider = LinkedInProvider(mock_account)

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": "urn:li:share:67890"}
    mock_post.return_value = mock_resp

    res = provider.publish_post("Hello LinkedIn")
    assert res["post_id"] == "urn:li:share:67890"
    assert res["url"] == "https://www.linkedin.com/feed/update/urn:li:share:67890"

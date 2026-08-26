from unittest.mock import MagicMock, mock_open, patch

import pytest

from socialmedia.models import SocialMediaAccount
from socialmedia.providers import (
    BaseSocialProvider,
    PublishingError,
    get_provider,
    get_provider_class,
)
from socialmedia.providers.bluesky import BlueskyProvider, extract_atproto_facets
from socialmedia.providers.buffer import BufferProvider
from socialmedia.providers.linkedin import LinkedInProvider
from socialmedia.providers.mastodon import MastodonProvider
from socialmedia.providers.postiz import PostizProvider
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
    assert provider.sync_campaign([]) == []


def test_registry_get_provider_class():
    assert get_provider_class("telegram") == TelegramProvider
    assert get_provider_class("mastodon") == MastodonProvider
    assert get_provider_class("twitter") == TwitterProvider
    assert get_provider_class("linkedin") == LinkedInProvider
    assert get_provider_class("bluesky") == BlueskyProvider
    assert get_provider_class("postiz") == PostizProvider
    assert get_provider_class("buffer") == BufferProvider
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


@patch("requests.post")
def test_postiz_publish_post_accepts_empty_success_response(mock_post, mock_account):
    mock_account.provider = "postiz"
    mock_account.credentials = {
        "api_url": "https://api.postiz.com",
        "api_key": "fake_key",
    }
    provider = PostizProvider(mock_account)
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_response.text = ""
    mock_post.return_value = mock_response

    res = provider.publish_post("Postiz status")

    assert res == {"post_id": "", "url": ""}


@patch("requests.post")
@patch("requests.get")
def test_postiz_send_test_message_creates_visible_post(
    mock_get, mock_post, mock_account
):
    mock_account.provider = "postiz"
    mock_account.credentials = {
        "api_url": "https://api.postiz.com",
        "api_key": "fake_key",
    }
    provider = PostizProvider(mock_account)

    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get.return_value = mock_get_response

    mock_post_response = MagicMock()
    mock_post_response.status_code = 201
    mock_post_response.json.return_value = {
        "id": "postiz_test_123",
        "url": "https://postiz.com/posts/postiz_test_123",
    }
    mock_post.return_value = mock_post_response

    result = provider.send_test_message()

    assert result["success"] is True
    assert "Test post created in Postiz" in result["message"]
    assert "postiz_test_123" in result["message"]
    assert mock_post.call_args.kwargs["json"] == {
        "content": "✅ Connection successful from Eventyay!"
    }


@patch("requests.post")
@patch("requests.get")
def test_postiz_send_test_message_handles_empty_success_response(
    mock_get, mock_post, mock_account
):
    mock_account.provider = "postiz"
    mock_account.credentials = {
        "api_url": "https://api.postiz.com",
        "api_key": "fake_key",
    }
    provider = PostizProvider(mock_account)

    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get.return_value = mock_get_response

    mock_post_response = MagicMock()
    mock_post_response.status_code = 204
    mock_post_response.text = ""
    mock_post.return_value = mock_post_response

    result = provider.send_test_message()

    assert result["success"] is True
    assert "Postiz accepted the request" in result["message"]


@patch("requests.post")
def test_buffer_validate_credentials(mock_post, mock_account):
    mock_account.provider = "buffer"
    mock_account.credentials = {
        "access_token": "fake_token",
    }
    provider = BufferProvider(mock_account)

    # Valid
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"account": {"id": "account123"}}}
    mock_post.return_value = mock_response
    assert provider.validate_credentials() is True

    # Invalid
    mock_response.json.return_value = {"data": {"account": None}}
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
    mock_response.json.return_value = {
        "data": {
            "createPost": {
                "post": {
                    "id": "buffer_123",
                    "text": "Buffer update",
                }
            }
        }
    }
    mock_post.return_value = mock_response

    res = provider.publish_post("Buffer update")
    assert res["post_id"] == "buffer_123"
    assert res["url"] == "https://publish.buffer.com/content/buffer_123"
    query = mock_post.call_args.kwargs["json"]["query"]
    assert 'channelId: "profile123"' in query
    assert "saveToDraft: false" in query


@patch("requests.post")
def test_buffer_send_test_message_creates_draft(mock_post, mock_account):
    mock_account.provider = "buffer"
    mock_account.platform_username = "profile123"
    mock_account.credentials = {
        "access_token": "fake_token",
    }
    provider = BufferProvider(mock_account)

    validate_response = MagicMock()
    validate_response.status_code = 200
    validate_response.json.return_value = {"data": {"account": {"id": "account123"}}}

    draft_response = MagicMock()
    draft_response.status_code = 200
    draft_response.json.return_value = {
        "data": {
            "createPost": {
                "post": {
                    "id": "draft_123",
                    "text": "✅ Connection successful from Eventyay!",
                }
            }
        }
    }
    mock_post.side_effect = [validate_response, draft_response]

    provider.send_test_message()


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


def test_bluesky_extract_atproto_facets():
    text = "Join us at https://eventyay.com for #fossasia and #tech conference!"
    facets = extract_atproto_facets(text)

    assert len(facets) == 3

    # Link facet
    link_facet = facets[0]
    assert link_facet["features"][0]["$type"] == "app.bsky.richtext.facet#link"
    assert link_facet["features"][0]["uri"] == "https://eventyay.com"
    byte_start = link_facet["index"]["byteStart"]
    byte_end = link_facet["index"]["byteEnd"]
    assert text.encode("utf-8")[byte_start:byte_end] == b"https://eventyay.com"

    # Tag facets
    tag_1 = facets[1]
    assert tag_1["features"][0]["$type"] == "app.bsky.richtext.facet#tag"
    assert tag_1["features"][0]["tag"] == "fossasia"

    tag_2 = facets[2]
    assert tag_2["features"][0]["$type"] == "app.bsky.richtext.facet#tag"
    assert tag_2["features"][0]["tag"] == "tech"


def test_bluesky_extract_atproto_facets_utf8_multibyte():
    # Text with emoji / unicode characters (multi-byte in UTF-8)
    text = "🎉 Hello 🚀 https://eventyay.com #conference"
    facets = extract_atproto_facets(text)
    assert len(facets) == 2

    link_facet = facets[0]
    byte_start = link_facet["index"]["byteStart"]
    byte_end = link_facet["index"]["byteEnd"]
    assert text.encode("utf-8")[byte_start:byte_end] == b"https://eventyay.com"

    tag_facet = facets[1]
    byte_start_t = tag_facet["index"]["byteStart"]
    byte_end_t = tag_facet["index"]["byteEnd"]
    assert text.encode("utf-8")[byte_start_t:byte_end_t] == b"#conference"


@patch("requests.post")
def test_bluesky_validate_credentials(mock_post, mock_account):
    mock_account.provider = "bluesky"
    mock_account.platform_username = "@test.bsky.social"
    mock_account.credentials = {
        "handle": "test.bsky.social",
        "app_password": "fake-app-password",
        "pds_url": "https://bsky.social",
    }
    provider = BlueskyProvider(mock_account)

    # Valid
    res_ok = MagicMock()
    res_ok.status_code = 200
    res_ok.json.return_value = {
        "accessJwt": "fake_jwt",
        "did": "did:plc:12345",
        "handle": "test.bsky.social",
    }
    mock_post.return_value = res_ok
    assert provider.validate_credentials() is True

    # Invalid (e.g. 401 Authentication Required)
    res_err = MagicMock()
    res_err.status_code = 401
    res_err.json.return_value = {"message": "Invalid identifier or password"}
    mock_post.return_value = res_err
    assert provider.validate_credentials() is False


@patch("requests.post")
def test_bluesky_publish_post_text_only(mock_post, mock_account):
    mock_account.provider = "bluesky"
    mock_account.platform_username = "@test.bsky.social"
    mock_account.credentials = {
        "handle": "test.bsky.social",
        "app_password": "fake-app-password",
        "pds_url": "https://bsky.social",
    }
    provider = BlueskyProvider(mock_account)

    # 1. createSession response
    res_session = MagicMock()
    res_session.status_code = 200
    res_session.json.return_value = {
        "accessJwt": "fake_jwt",
        "did": "did:plc:12345",
        "handle": "test.bsky.social",
    }

    # 2. createRecord response
    res_record = MagicMock()
    res_record.status_code = 200
    res_record.json.return_value = {
        "uri": "at://did:plc:12345/app.bsky.feed.post/3l7example",
        "cid": "bafyreiexample",
    }

    mock_post.side_effect = [res_session, res_record]

    res = provider.publish_post("Hello Bluesky from https://eventyay.com #eventyay")
    assert res["post_id"] == "3l7example"
    assert res["url"] == "https://bsky.app/profile/test.bsky.social/post/3l7example"

    # Verify createRecord payload
    create_call = mock_post.call_args_list[1]
    payload = create_call.kwargs["json"]
    assert payload["repo"] == "did:plc:12345"
    assert payload["collection"] == "app.bsky.feed.post"
    assert (
        payload["record"]["text"] == "Hello Bluesky from https://eventyay.com #eventyay"
    )
    assert len(payload["record"]["facets"]) == 2


@patch("socialmedia.providers.bluesky._safe_fetch_url")
@patch("requests.post")
def test_bluesky_publish_post_with_media(mock_post, mock_fetch, mock_account):
    mock_account.provider = "bluesky"
    mock_account.platform_username = "@test.bsky.social"
    mock_account.credentials = {
        "handle": "test.bsky.social",
        "app_password": "fake-app-password",
        "pds_url": "https://bsky.social",
    }
    provider = BlueskyProvider(mock_account)

    # 1. createSession response
    res_session = MagicMock()
    res_session.status_code = 200
    res_session.json.return_value = {
        "accessJwt": "fake_jwt",
        "did": "did:plc:12345",
        "handle": "test.bsky.social",
    }

    # Mock media fetch
    res_fetch = MagicMock()
    res_fetch.content = b"fake_image_bytes"
    res_fetch.headers = {"Content-Type": "image/png"}
    mock_fetch.return_value = res_fetch

    # 2. uploadBlob response
    res_blob = MagicMock()
    res_blob.status_code = 200
    res_blob.json.return_value = {
        "blob": {
            "$type": "blob",
            "ref": {"$link": "blob_cid_123"},
            "mimeType": "image/png",
            "size": 16,
        }
    }

    # 3. createRecord response
    res_record = MagicMock()
    res_record.status_code = 200
    res_record.json.return_value = {
        "uri": "at://did:plc:12345/app.bsky.feed.post/3l7mediaexample",
        "cid": "bafyreiimage",
    }

    mock_post.side_effect = [res_session, res_blob, res_record]

    res = provider.publish_post(
        "Bluesky with photo",
        media=["https://example.com/speaker.png"],
    )
    assert res["post_id"] == "3l7mediaexample"
    assert (
        res["url"] == "https://bsky.app/profile/test.bsky.social/post/3l7mediaexample"
    )

    # Verify uploadBlob was called with correct auth
    upload_call = mock_post.call_args_list[1]
    assert upload_call.kwargs["headers"]["Authorization"] == "Bearer fake_jwt"
    assert upload_call.kwargs["headers"]["Content-Type"] == "image/png"
    assert upload_call.kwargs["data"] == b"fake_image_bytes"

    # Verify createRecord has embed images
    create_call = mock_post.call_args_list[2]
    payload = create_call.kwargs["json"]
    assert "embed" in payload["record"]
    assert payload["record"]["embed"]["$type"] == "app.bsky.embed.images"
    assert len(payload["record"]["embed"]["images"]) == 1


@patch("requests.post")
def test_bluesky_send_test_message(mock_post, mock_account):
    mock_account.provider = "bluesky"
    mock_account.platform_username = "@test.bsky.social"
    mock_account.credentials = {
        "handle": "test.bsky.social",
        "app_password": "fake-app-password",
        "pds_url": "https://bsky.social",
    }
    provider = BlueskyProvider(mock_account)

    res_session = MagicMock()
    res_session.status_code = 200
    res_session.json.return_value = {
        "accessJwt": "fake_jwt",
        "did": "did:plc:12345",
        "handle": "test.bsky.social",
    }

    res_record = MagicMock()
    res_record.status_code = 200
    res_record.json.return_value = {
        "uri": "at://did:plc:12345/app.bsky.feed.post/3l7testexample",
        "cid": "bafyreitest",
    }

    mock_post.side_effect = [res_session, res_record]

    result = provider.send_test_message()
    assert result["success"] is True
    assert "3l7testexample" in result["message"]
    assert (
        result["url"] == "https://bsky.app/profile/test.bsky.social/post/3l7testexample"
    )


@patch("requests.post")
def test_bluesky_publish_post_error(mock_post, mock_account):
    mock_account.provider = "bluesky"
    mock_account.platform_username = "@test.bsky.social"
    mock_account.credentials = {
        "handle": "test.bsky.social",
        "app_password": "fake-app-password",
        "pds_url": "https://bsky.social",
    }
    provider = BlueskyProvider(mock_account)

    res_session = MagicMock()
    res_session.status_code = 200
    res_session.json.return_value = {
        "accessJwt": "fake_jwt",
        "did": "did:plc:12345",
        "handle": "test.bsky.social",
    }

    res_record_err = MagicMock()
    res_record_err.status_code = 400
    res_record_err.json.return_value = {"message": "Post text too long"}

    mock_post.side_effect = [res_session, res_record_err]

    with pytest.raises(PublishingError, match="Bluesky post creation failed"):
        provider.publish_post("text")

import pytest

from socialmedia.crypto import (
    decrypt_credentials,
    encrypt_credentials,
)
from socialmedia.models import SocialMediaAccount


def test_encryption_decryption_roundtrip():
    # Setup test data
    secret_data = {
        "access_token": "super-secret-token-12345",
        "instance_url": "https://mastodon.social",
        "chat_id": -100123456789,
    }

    # Encrypt
    encrypted_text = encrypt_credentials(secret_data)
    assert isinstance(encrypted_text, str)
    assert len(encrypted_text) > 0
    assert "super-secret-token" not in encrypted_text

    # Decrypt
    decrypted_data = decrypt_credentials(encrypted_text)
    assert decrypted_data == secret_data


def test_decryption_empty_or_invalid():
    # Decrypt empty strings or None should return empty dict
    assert decrypt_credentials("") == {}
    assert decrypt_credentials(None) == {}
    assert decrypt_credentials("invalid-encrypted-blob") == {}


def test_encryption_empty_or_none():
    assert encrypt_credentials({}) == ""
    assert encrypt_credentials(None) == ""


@pytest.mark.django_db
def test_social_media_account_credentials_property(organizer):
    from django_scopes import scope

    with scope(organizer=organizer):
        account = SocialMediaAccount.objects.create(
            organizer=organizer,
            provider="mastodon",
            platform_username="test_user",
        )

        credentials_payload = {
            "access_token": "token-xyz",
            "instance_url": "https://mastodon.social",
        }

        # Set credentials via property
        account.credentials = credentials_payload
        account.save()

        # Re-fetch from DB
        db_account = SocialMediaAccount.objects.get(pk=account.pk)
        assert db_account.encrypted_credentials != ""
        assert "token-xyz" not in db_account.encrypted_credentials
        assert db_account.credentials == credentials_payload

from unittest.mock import MagicMock

from socialmedia.export import _extract_speaker_social_info, safe_format


class DummyLink:
    def __init__(self, network, url, path=""):
        self.network = network
        self.url = url
        self.path = path


class DummySpeaker:
    def __init__(self, display_name="Alice Smith", links=None):
        self._display_name = display_name
        self.pk = 1
        self.code = "ALICE1"
        self._links = links or []

    def get_display_name(self):
        return self._display_name

    @property
    def social_links(self):
        manager = MagicMock()
        manager.all.return_value = self._links
        return manager


def test_extract_speaker_social_info_empty():
    info, links = _extract_speaker_social_info(None)
    assert info["speaker_social_handle"] == ""
    assert links == []


def test_extract_speaker_social_info_with_links():
    speaker = DummySpeaker(
        "Alice Smith",
        links=[
            DummyLink("twitter", "https://x.com/alice_smith", "alice_smith"),
            DummyLink("linkedin", "https://linkedin.com/in/alice-smith", "alice-smith"),
        ],
    )
    info, links = _extract_speaker_social_info(speaker, target_platform="twitter")
    assert info["speaker_social_handle"] == "@alice_smith"
    assert info["speaker_twitter"] == "@alice_smith"
    assert info["speaker_linkedin"] == "@alice-smith"
    assert info["speaker_linkedin_url"] == "https://linkedin.com/in/alice-smith"
    assert len(links) == 2
    assert links[0]["network"] == "twitter"
    assert links[0]["handle"] == "@alice_smith"


def test_extract_speaker_social_info_target_platform_mismatch():
    speaker = DummySpeaker(
        "Bob Jones",
        links=[
            DummyLink("linkedin", "https://linkedin.com/in/bob-jones", "bob-jones"),
        ],
    )
    # Target platform is twitter, but speaker only has linkedin
    info, links = _extract_speaker_social_info(speaker, target_platform="twitter")
    assert info["speaker_social_handle"] == ""
    assert info["speaker_linkedin"] == "@bob-jones"
    assert info["speaker_linkedin_url"] == "https://linkedin.com/in/bob-jones"


def test_safe_format_with_handles():
    tmpl = "Meet {speaker_name} ({speaker_social_handle}) at {event_name}!"
    out = safe_format(
        tmpl, speaker_name="Alice", speaker_social_handle="@alice", event_name="PyCon"
    )
    assert out == "Meet Alice (@alice) at PyCon!"


def test_safe_format_empty_handle_cleanup():
    tmpl = "Meet {speaker_name} ({speaker_social_handle}) [{speaker_twitter}] at {event_name}!"
    out = safe_format(
        tmpl,
        speaker_name="Alice",
        speaker_social_handle="",
        speaker_twitter="",
        event_name="PyCon",
    )
    assert out == "Meet Alice at PyCon!"


def test_extract_speaker_social_info_user_instance():
    profile = DummySpeaker(
        "Alice User",
        links=[DummyLink("twitter", "https://x.com/alice_user", "alice_user")],
    )
    user = MagicMock()
    user.event_profile.return_value = profile
    event = MagicMock()

    info, links = _extract_speaker_social_info(user, event=event)
    assert info["speaker_social_handle"] == "@alice_user"
    assert len(links) == 1


def test_custom_template_priority_over_platform_defaults():
    event = MagicMock()
    event.settings.get.side_effect = lambda key, default=None, **kwargs: (
        "Custom Speaker Template {speaker_name} ({speaker_social_handle})"
        if key == "socialmedia_speaker_template"
        else default
    )
    from socialmedia.export import _get_platform_template

    tpl = _get_platform_template(event, "speaker", "twitter", "announcement")
    assert tpl == "Custom Speaker Template {speaker_name} ({speaker_social_handle})"


def test_platform_default_templates_contain_social_handles():
    from socialmedia.export import PLATFORM_DEFAULT_TEMPLATES

    for platform in ["twitter", "telegram", "linkedin", "mastodon"]:
        speaker_tpl = PLATFORM_DEFAULT_TEMPLATES[platform]["speaker"]["announcement"]
        assert "{speaker_social_handle}" in speaker_tpl, (
            f"Missing in {platform} speaker announcement"
        )

        session_tpl = PLATFORM_DEFAULT_TEMPLATES[platform]["session"]["announcement"]
        assert "{speaker_social_handles}" in session_tpl, (
            f"Missing in {platform} session announcement"
        )

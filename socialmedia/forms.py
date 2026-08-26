from django import forms
from django.utils.translation import gettext_lazy as _
from eventyay.base.forms import SettingsForm

from .export import DEFAULT_TEMPLATES, PLATFORMS
from .models import SocialMediaAccount
from .telegram_utils import normalize_telegram_chat_id

MAX_OFFSETS = 10
MAX_OFFSET_VALUE_CFP = 365
MAX_OFFSET_VALUE_SPEAKER = 365
MAX_OFFSET_VALUE_SESSION = 1440
MAX_OFFSET_VALUE_TICKET = 365
MAX_OFFSET_VALUE_SCHEDULE = 90

# Display order for platforms in the UI
PLATFORM_ORDER = ["twitter", "bluesky", "linkedin", "telegram", "mastodon"]

# Character limits per platform (None means no enforced limit)
PLATFORM_CHAR_LIMITS = {
    "twitter": 280,
    "bluesky": 300,
    "mastodon": 500,
    "telegram": None,
    "linkedin": None,
}

# Extra help-text hints per platform
_PLATFORM_HINTS = {
    "twitter": "≤280 chars.",
    "bluesky": "≤300 chars.",
    "mastodon": "≤500 chars.",
    "telegram": "Markdown supported.",
    "linkedin": "Professional tone.",
}

# Available placeholder tokens per post type
_TYPE_TOKENS = {
    "cfp": "{event_name}, {cfp_deadline}, {cfp_link}, {hashtags}",
    "speaker": "{event_name}, {speaker_name}, {speaker_link}, {talk_title}, {hashtags}",
    "session": (
        "{event_name}, {talk_title}, {talk_room}, {talk_start_time}, "
        "{speaker_names}, {talk_link}, {hashtags}"
    ),
    "ticket": "{event_name}, {ticket_name}, {ticket_price}, {ticket_link}, {hashtags}",
    "schedule": "{event_name}, {schedule_link}, {hashtags}",
}

# Human-readable post-type labels
_TYPE_LABELS = {
    "cfp": "CFP",
    "speaker": "Speaker",
    "session": "Session",
    "ticket": "Ticket",
    "schedule": "Schedule",
}


def _validate_offsets(value, max_value, unit_label="days"):
    """Validate a comma-separated offset field.  Returns the cleaned string
    or raises ValidationError."""
    if not value or not value.strip():
        return value
    raw = str(value).strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) > MAX_OFFSETS:
        raise forms.ValidationError(
            _("Enter at most %(count)s offsets."),
            params={"count": MAX_OFFSETS},
        )
    seen = set()
    cleaned = []
    for part in parts:
        try:
            val = int(part)
        except ValueError as e:
            raise forms.ValidationError(
                _('"%(value)s" is not a valid number.'),
                params={"value": part},
            ) from e
        if val < 0:
            raise forms.ValidationError(
                _("Offset must be zero or positive."),
            )
        if val > max_value:
            raise forms.ValidationError(
                _("Offset %(value)s exceeds maximum of %(max)s %(unit)s."),
                params={"value": val, "max": max_value, "unit": unit_label},
            )
        if val not in seen:
            seen.add(val)
            cleaned.append(val)
    return ", ".join(str(v) for v in sorted(cleaned, reverse=True))


def _check_platform_char_limit(value, limit, platform_name):
    """Raise ValidationError if the template text (excluding {token} placeholders)
    already exceeds the platform character limit."""
    import re

    if not value or not limit:
        return value
    stripped = re.sub(r"\{[^}]+\}", "", value)
    if len(stripped) > limit:
        raise forms.ValidationError(
            _(
                "The template text (excluding placeholders) is %(length)s characters, "
                "which already exceeds the %(platform)s limit of %(limit)s characters. "
                "Shorten the template so interpolated posts fit within the limit."
            ),
            params={
                "length": len(stripped),
                "platform": platform_name,
                "limit": limit,
            },
        )
    return value


class SocialMediaSettingsForm(SettingsForm):
    # ------------------------------------------------------------------
    # Global settings
    # ------------------------------------------------------------------
    socialmedia_event_link = forms.URLField(
        label=_("Custom Event Link"),
        help_text=_(
            "Override the public URL used in posts. "
            "Leave blank to use the event's default page URL."
        ),
        required=False,
    )
    socialmedia_default_hashtags = forms.CharField(
        label=_("Default Hashtags"),
        help_text=_(
            "Space-separated hashtags appended to every post. "
            "E.g. #fossasia #conference"
        ),
        required=False,
        max_length=200,
    )
    socialmedia_auto_publish = forms.BooleanField(
        label=_("Automatically Publish Scheduled Posts"),
        help_text=_(
            "When enabled, scheduled posts for direct integrations (e.g. Telegram, Mastodon) "
            "are published automatically at their scheduled time by the background worker. "
            "When disabled, posts remain as drafts until manually approved or pinned."
        ),
        required=False,
        initial=True,
    )

    # ------------------------------------------------------------------
    # Platform toggles  (order: Twitter, LinkedIn, Telegram, Mastodon)
    # ------------------------------------------------------------------
    socialmedia_twitter_enabled = forms.BooleanField(
        label=_("Enable X / Twitter"),
        help_text=_(
            "Generate separate draft posts optimised for X / Twitter (≤280 chars)."
        ),
        required=False,
        initial=False,
    )
    socialmedia_bluesky_enabled = forms.BooleanField(
        label=_("Enable Bluesky"),
        help_text=_(
            "Generate separate draft posts for Bluesky (≤300 chars, AT Protocol)."
        ),
        required=False,
        initial=False,
    )
    socialmedia_linkedin_enabled = forms.BooleanField(
        label=_("Enable LinkedIn"),
        help_text=_(
            "Generate separate draft posts for LinkedIn (long-form, professional tone)."
        ),
        required=False,
        initial=False,
    )
    socialmedia_telegram_enabled = forms.BooleanField(
        label=_("Enable Telegram"),
        help_text=_(
            "Generate separate draft posts for Telegram (Markdown formatting)."
        ),
        required=False,
        initial=False,
    )
    socialmedia_mastodon_enabled = forms.BooleanField(
        label=_("Enable Mastodon"),
        help_text=_("Generate separate draft posts for Mastodon (≤500 chars)."),
        required=False,
        initial=False,
    )

    # Per-platform × per-type template fields are generated dynamically
    # in __init__() below via PLATFORM_ORDER × _TYPE_LABELS.

    # ------------------------------------------------------------------
    # CFP
    # ------------------------------------------------------------------
    socialmedia_cfp_enabled = forms.BooleanField(
        label=_("Enable CFP posts"),
        required=False,
        initial=True,
    )
    socialmedia_cfp_offset = forms.CharField(
        label=_("Days before CFP deadline"),
        help_text=_(
            "Days before deadline to schedule. Enter a number or "
            "comma-separated values (e.g., 14, 7, 1). "
            "Leave blank to use the default of 7."
        ),
        required=False,
        initial="7",
    )
    socialmedia_cfp_template = forms.CharField(
        label=_("CFP post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {cfp_deadline}, {cfp_link}, {hashtags}. "
            "Note: A custom template here overrides all schedule waves "
            "(announcement, reminder, final call) with identical text."
        ),
    )

    # ------------------------------------------------------------------
    # Speaker
    # ------------------------------------------------------------------
    socialmedia_speaker_enabled = forms.BooleanField(
        label=_("Enable Speaker posts"),
        required=False,
        initial=True,
    )
    socialmedia_speaker_offset = forms.CharField(
        label=_("Days before session (speakers)"),
        help_text=_(
            "Days before speaker's session. Enter a number or "
            "comma-separated values (e.g., 30, 7, 1). "
            "Leave blank to use the default of 3."
        ),
        required=False,
        initial="3",
    )
    socialmedia_speaker_template = forms.CharField(
        label=_("Speaker post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {speaker_name}, {speaker_link}, "
            "{talk_title}, {hashtags}. "
            "Note: A custom template here overrides all schedule waves "
            "(announcement, reminder, final call) with identical text."
        ),
    )

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    socialmedia_session_enabled = forms.BooleanField(
        label=_("Enable Session posts"),
        required=False,
        initial=True,
    )
    socialmedia_session_offset = forms.CharField(
        label=_("Minutes before session"),
        help_text=_(
            "Minutes before session starts. Enter a number or "
            "comma-separated values (e.g., 60, 30, 15). "
            "Leave blank to use the default of 30."
        ),
        required=False,
        initial="30",
    )
    socialmedia_session_template = forms.CharField(
        label=_("Session post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {talk_title}, {talk_room}, {talk_start_time}, "
            "{speaker_names}, {talk_link}, {hashtags}. "
            "Note: A custom template here overrides all schedule waves "
            "(announcement, reminder, final call) with identical text."
        ),
    )

    # ------------------------------------------------------------------
    # Ticket
    # ------------------------------------------------------------------
    socialmedia_ticket_enabled = forms.BooleanField(
        label=_("Enable Ticket posts"),
        required=False,
        initial=True,
    )
    socialmedia_ticket_offset = forms.CharField(
        label=_("Days before event (tickets)"),
        help_text=_(
            "Days before event starts. Enter a number or "
            "comma-separated values (e.g., 30, 14, 5). "
            "Leave blank to use the default of 5."
        ),
        required=False,
        initial="5",
    )
    socialmedia_ticket_template = forms.CharField(
        label=_("Ticket post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {ticket_name}, {ticket_price}, "
            "{ticket_link}, {hashtags}. "
            "Note: A custom template here overrides all schedule waves "
            "(announcement, reminder, final call) with identical text."
        ),
    )

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------
    socialmedia_schedule_enabled = forms.BooleanField(
        label=_("Enable Schedule posts"),
        required=False,
        initial=True,
    )
    socialmedia_schedule_offset = forms.CharField(
        label=_("Days before event (schedule)"),
        help_text=_(
            "Days before event to announce schedule. Enter a number or "
            "comma-separated values (e.g., 7, 2). "
            "Leave blank to use the default of 2."
        ),
        required=False,
        initial="2",
    )
    socialmedia_schedule_template = forms.CharField(
        label=_("Schedule post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {schedule_link}, {hashtags}. "
            "Note: A custom template here overrides all schedule waves "
            "(announcement, reminder, final call) with identical text."
        ),
    )

    @property
    def default_template_preview(self):
        """Return the baked-in defaults for display in the UI."""

        class _AttrDict(dict):
            """Dict subclass that supports attribute-style access for
            Django templates."""

            def __getattr__(self, item):
                try:
                    return self[item]
                except KeyError as e:
                    raise AttributeError(item) from e

        return _AttrDict(DEFAULT_TEMPLATES)

    # ------------------------------------------------------------------
    # Offset validation
    # ------------------------------------------------------------------
    def clean_socialmedia_cfp_offset(self):
        return _validate_offsets(
            self.cleaned_data.get("socialmedia_cfp_offset"),
            MAX_OFFSET_VALUE_CFP,
            "days",
        )

    def clean_socialmedia_speaker_offset(self):
        return _validate_offsets(
            self.cleaned_data.get("socialmedia_speaker_offset"),
            MAX_OFFSET_VALUE_SPEAKER,
            "days",
        )

    def clean_socialmedia_session_offset(self):
        return _validate_offsets(
            self.cleaned_data.get("socialmedia_session_offset"),
            MAX_OFFSET_VALUE_SESSION,
            "minutes",
        )

    def clean_socialmedia_ticket_offset(self):
        return _validate_offsets(
            self.cleaned_data.get("socialmedia_ticket_offset"),
            MAX_OFFSET_VALUE_TICKET,
            "days",
        )

    def clean_socialmedia_schedule_offset(self):
        return _validate_offsets(
            self.cleaned_data.get("socialmedia_schedule_offset"),
            MAX_OFFSET_VALUE_SCHEDULE,
            "days",
        )

    # ------------------------------------------------------------------
    # Dynamic per-platform template field generation
    # ------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate per-platform × per-type template fields.
        # Field order follows PLATFORM_ORDER × _TYPE_LABELS.
        for platform in PLATFORM_ORDER:
            platform_label = PLATFORMS[platform]
            hint = _PLATFORM_HINTS.get(platform, "")
            rows = 3 if platform == "linkedin" else 2
            for post_type, type_label in _TYPE_LABELS.items():
                tokens = _TYPE_TOKENS[post_type]
                field_name = f"socialmedia_{platform}_{post_type}_template"
                help_parts = [
                    f"Leave blank to use the {platform_label}-specific default."
                ]
                if hint:
                    help_parts.append(hint)
                help_parts.append(f"Available: {tokens}")
                self.fields[field_name] = forms.CharField(
                    label=f"{platform_label} \u2014 {type_label} template",
                    widget=forms.Textarea(attrs={"rows": rows}),
                    required=False,
                    help_text=" ".join(help_parts),
                )

    # ------------------------------------------------------------------
    # Per-platform character limit validation (helper, called by generated methods)
    # ------------------------------------------------------------------
    def _clean_platform_template(self, field_name, platform):
        value = self.cleaned_data.get(field_name, "")
        limit = PLATFORM_CHAR_LIMITS.get(platform)
        platform_label = PLATFORMS.get(platform, platform)
        return _check_platform_char_limit(value, limit, platform_label)


def _add_platform_clean_methods():
    """Dynamically attach clean_<field>() methods to SocialMediaSettingsForm
    for all platform × type combinations that have a character limit."""
    for platform in PLATFORM_ORDER:
        if PLATFORM_CHAR_LIMITS.get(platform) is None:
            continue
        for post_type in _TYPE_LABELS:
            field_name = f"socialmedia_{platform}_{post_type}_template"
            method_name = f"clean_{field_name}"

            def _make_cleaner(fn, pl):
                def cleaner(self):
                    return self._clean_platform_template(fn, pl)

                cleaner.__name__ = f"clean_{fn}"
                return cleaner

            setattr(
                SocialMediaSettingsForm,
                method_name,
                _make_cleaner(field_name, platform),
            )


_add_platform_clean_methods()


class TelegramAccountForm(forms.ModelForm):
    bot_token = forms.CharField(
        label=_("Bot API Token"),
        widget=forms.PasswordInput(render_value=True),
        help_text=_("The API token for your Telegram Bot (e.g. from @BotFather)"),
        required=True,
    )

    class Meta:
        model = SocialMediaAccount
        fields = ["platform_username", "is_active"]
        labels = {
            "platform_username": _("Channel/Chat ID"),
        }
        help_texts = {
            "platform_username": _(
                "Use @publicusername for public chats/channels or the numeric chat "
                "ID for private groups, e.g. -100123456789. Invite links cannot be "
                "used as chat IDs."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            creds = self.instance.credentials
            if creds.get("bot_token"):
                self.fields["bot_token"].initial = "••••••••"
                self.fields["bot_token"].required = False

    def clean_bot_token(self):
        token = self.cleaned_data.get("bot_token")
        if (not token or token == "••••••••") and self.instance and self.instance.pk:
            creds = self.instance.credentials
            return creds.get("bot_token")
        return token.strip() if token else token

    def clean_platform_username(self):
        value = (self.cleaned_data.get("platform_username") or "").strip()
        if "t.me/+" in value or "t.me/joinchat/" in value:
            raise forms.ValidationError(
                _(
                    "Telegram invite links cannot be used here. Use a public "
                    "@username or the numeric chat ID, usually starting with -100."
                )
            )
        return normalize_telegram_chat_id(value)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = "telegram"
        instance.credentials = {
            "bot_token": self.cleaned_data.get("bot_token"),
        }
        if commit:
            instance.save()
        return instance


class MastodonAccountForm(forms.ModelForm):
    api_base_url = forms.URLField(
        label=_("Instance URL"),
        help_text=_("e.g. https://mastodon.social"),
        required=True,
    )
    access_token = forms.CharField(
        label=_("Access Token"),
        widget=forms.PasswordInput(render_value=True),
        required=True,
    )

    class Meta:
        model = SocialMediaAccount
        fields = ["platform_username", "is_active"]
        labels = {
            "platform_username": _("Mastodon Username Handle"),
        }
        help_texts = {
            "platform_username": _("e.g. @myuser@mastodon.social"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            creds = self.instance.credentials
            if creds.get("api_base_url"):
                self.fields["api_base_url"].initial = creds.get("api_base_url")
            if creds.get("access_token"):
                self.fields["access_token"].initial = "••••••••"
                self.fields["access_token"].required = False

    def clean_access_token(self):
        token = self.cleaned_data.get("access_token")
        if (not token or token == "••••••••") and self.instance and self.instance.pk:
            creds = self.instance.credentials
            return creds.get("access_token")
        return token.strip() if token else token

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = "mastodon"
        instance.credentials = {
            "api_base_url": self.cleaned_data.get("api_base_url"),
            "access_token": self.cleaned_data.get("access_token"),
        }
        if commit:
            instance.save()
        return instance


class PostizAccountForm(forms.ModelForm):
    api_url = forms.URLField(
        label=_("API Instance URL"),
        help_text=_("e.g. https://api.postiz.com or self-hosted endpoint"),
        required=True,
    )
    api_key = forms.CharField(
        label=_("API Key"),
        widget=forms.PasswordInput(render_value=True),
        required=True,
    )

    class Meta:
        model = SocialMediaAccount
        fields = ["platform_username", "is_active"]
        labels = {
            "platform_username": _("Configuration Name"),
        }
        help_texts = {
            "platform_username": _("e.g. My Organization Postiz Link"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            creds = self.instance.credentials
            if creds.get("api_url"):
                self.fields["api_url"].initial = creds.get("api_url")
            if creds.get("api_key"):
                self.fields["api_key"].initial = "••••••••"
                self.fields["api_key"].required = False

    def clean_api_key(self):
        key = self.cleaned_data.get("api_key")
        if (not key or key == "••••••••") and self.instance and self.instance.pk:
            creds = self.instance.credentials
            return creds.get("api_key")
        return key.strip() if key else key

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = "postiz"
        instance.credentials = {
            "api_url": self.cleaned_data.get("api_url"),
            "api_key": self.cleaned_data.get("api_key"),
        }
        if commit:
            instance.save()
        return instance


class BufferAccountForm(forms.ModelForm):
    access_token = forms.CharField(
        label=_("Access Token"),
        widget=forms.PasswordInput(render_value=True),
        required=True,
    )

    class Meta:
        model = SocialMediaAccount
        fields = ["platform_username", "is_active"]
        labels = {
            "platform_username": _("Buffer Channel ID"),
        }
        help_texts = {
            "platform_username": _(
                "The id of the connected Buffer channel/profile you want to post to."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            creds = self.instance.credentials
            if creds.get("access_token"):
                self.fields["access_token"].initial = "••••••••"
                self.fields["access_token"].required = False

    def clean_access_token(self):
        token = self.cleaned_data.get("access_token")
        if (not token or token == "••••••••") and self.instance and self.instance.pk:
            creds = self.instance.credentials
            return creds.get("access_token")
        return token.strip() if token else token

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = "buffer"
        instance.credentials = {
            "access_token": self.cleaned_data.get("access_token"),
        }
        if commit:
            instance.save()
        return instance


class TwitterAccountForm(forms.ModelForm):
    api_key = forms.CharField(
        label=_("API Key (Consumer Key)"),
        widget=forms.PasswordInput(render_value=True),
        required=True,
    )
    api_secret = forms.CharField(
        label=_("API Secret (Consumer Secret)"),
        widget=forms.PasswordInput(render_value=True),
        required=True,
    )
    access_token = forms.CharField(
        label=_("Access Token"),
        widget=forms.PasswordInput(render_value=True),
        required=True,
    )
    access_token_secret = forms.CharField(
        label=_("Access Token Secret"),
        widget=forms.PasswordInput(render_value=True),
        required=True,
    )

    class Meta:
        model = SocialMediaAccount
        fields = ["platform_username", "is_active"]
        labels = {
            "platform_username": _("Twitter/X Handle"),
        }
        help_texts = {
            "platform_username": _("e.g. @eventyay"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            creds = self.instance.credentials
            fields = [
                "api_key",
                "api_secret",
                "access_token",
                "access_token_secret",
            ]
            for field_name in fields:
                if creds.get(field_name):
                    self.fields[field_name].initial = "••••••••"
                    self.fields[field_name].required = False

    def _clean_credential(self, field_name):
        val = self.cleaned_data.get(field_name)
        if (not val or val == "••••••••") and self.instance and self.instance.pk:
            return self.instance.credentials.get(field_name)
        return val.strip() if val else val

    def clean_api_key(self):
        return self._clean_credential("api_key")

    def clean_api_secret(self):
        return self._clean_credential("api_secret")

    def clean_access_token(self):
        return self._clean_credential("access_token")

    def clean_access_token_secret(self):
        return self._clean_credential("access_token_secret")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = "twitter"
        instance.credentials = {
            "api_key": self.cleaned_data.get("api_key"),
            "api_secret": self.cleaned_data.get("api_secret"),
            "access_token": self.cleaned_data.get("access_token"),
            "access_token_secret": self.cleaned_data.get("access_token_secret"),
        }
        if commit:
            instance.save()
        return instance


class LinkedInAccountForm(forms.ModelForm):
    access_token = forms.CharField(
        label=_("Access Token"),
        widget=forms.PasswordInput(render_value=True),
        required=False,
        help_text=_(
            "Paste your LinkedIn access token here, OR fill in Client ID, "
            "Client Secret, and Authorization Code below to generate one."
        ),
    )
    client_id = forms.CharField(
        label=_("Client ID"),
        required=False,
        help_text=_(
            "From LinkedIn Developer Portal → Auth tab → Application credentials"
        ),
    )
    client_secret = forms.CharField(
        label=_("Client Secret"),
        widget=forms.PasswordInput(render_value=True),
        required=False,
        help_text=_(
            "From LinkedIn Developer Portal → Auth tab → Application credentials"
        ),
    )
    authorization_code = forms.CharField(
        label=_("Authorization Code"),
        required=False,
        help_text=_(
            "The code from the OAuth redirect URL after authorizing your app. "
            "See setup instructions for details."
        ),
    )
    author_urn = forms.CharField(
        label=_("Author URN"),
        help_text=_(
            "Optional for personal profiles (leave blank to auto-detect). "
            "For company pages, enter urn:li:organization:YOUR_PAGE_ID."
        ),
        required=False,
    )

    class Meta:
        model = SocialMediaAccount
        fields = ["platform_username", "is_active"]
        labels = {
            "platform_username": _("LinkedIn Profile/Page Name"),
        }
        help_texts = {
            "platform_username": _("e.g. Eventyay Organization Page"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            creds = self.instance.credentials
            if creds.get("author_urn"):
                self.fields["author_urn"].initial = creds.get("author_urn")
            if creds.get("access_token"):
                self.fields["access_token"].initial = "••••••••"
                self.fields["client_id"].initial = creds.get("client_id", "")
                # Don't show client_secret

    def clean(self):
        cleaned_data = super().clean()
        access_token = cleaned_data.get("access_token")
        client_id = cleaned_data.get("client_id")
        client_secret = cleaned_data.get("client_secret")
        auth_code = cleaned_data.get("authorization_code")

        # If token is masked and no OAuth credentials provided, keep existing
        if (
            (not access_token or access_token == "••••••••")
            and self.instance
            and self.instance.pk
        ):
            existing_token = self.instance.credentials.get("access_token")
            if existing_token:
                cleaned_data["access_token"] = existing_token

        # Exchange authorization code for access token
        if auth_code and client_id and client_secret:
            import requests as http_requests

            try:
                resp = http_requests.post(
                    "https://www.linkedin.com/oauth/v2/accessToken",
                    data={
                        "grant_type": "authorization_code",
                        "code": auth_code,
                        "redirect_uri": "https://localhost",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    try:
                        token_data = resp.json()
                    except Exception:
                        raise forms.ValidationError(
                            _("LinkedIn token exchange failed: %(error)s"),
                            params={"error": resp.text[:200]},
                        )
                    cleaned_data["access_token"] = token_data.get("access_token")
                else:
                    try:
                        error_msg = (
                            resp.json().get("error_description") or resp.text[:200]
                        )
                    except Exception:
                        error_msg = resp.text[:200]
                    raise forms.ValidationError(
                        _("LinkedIn token exchange failed: %(error)s"),
                        params={"error": error_msg},
                    )
            except http_requests.RequestException as e:
                raise forms.ValidationError(
                    _("Could not connect to LinkedIn: %(error)s"),
                    params={"error": str(e)},
                ) from e
        elif auth_code and (not client_id or not client_secret):
            raise forms.ValidationError(
                _(
                    "Client ID and Client Secret are required when using "
                    "Authorization Code."
                )
            )

        return cleaned_data

    def clean_access_token(self):
        token = self.cleaned_data.get("access_token")
        if (not token or token == "••••••••") and self.instance and self.instance.pk:
            return self.instance.credentials.get("access_token")
        return token.strip() if token else token

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = "linkedin"
        instance.credentials = {
            "access_token": self.cleaned_data.get("access_token"),
            "author_urn": (self.cleaned_data.get("author_urn") or "").strip(),
            "client_id": (self.cleaned_data.get("client_id") or "").strip(),
        }
        if commit:
            instance.save()
        return instance


class BlueskyAccountForm(forms.ModelForm):
    handle = forms.CharField(
        label=_("Bluesky Handle"),
        help_text=_("e.g. user.bsky.social or your custom domain handle"),
        required=True,
    )
    app_password = forms.CharField(
        label=_("App Password"),
        widget=forms.PasswordInput(render_value=True),
        help_text=_(
            "Create an App Password in Bluesky Settings → Advanced → App passwords. "
            "Do not use your main account password."
        ),
        required=True,
    )
    pds_url = forms.URLField(
        label=_("PDS / Server URL"),
        initial="https://bsky.social",
        help_text=_(
            "Personal Data Server host. Default is https://bsky.social for standard Bluesky accounts."
        ),
        required=False,
    )

    class Meta:
        model = SocialMediaAccount
        fields = ["platform_username", "is_active"]
        labels = {
            "platform_username": _("Display Name / Account Note"),
        }
        help_texts = {
            "platform_username": _(
                "Optional display name for this account in Eventyay."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["platform_username"].required = False
        if self.instance and self.instance.pk:
            creds = self.instance.credentials
            if creds.get("handle"):
                self.fields["handle"].initial = creds.get("handle")
            if creds.get("pds_url"):
                self.fields["pds_url"].initial = creds.get("pds_url")
            if creds.get("app_password"):
                self.fields["app_password"].initial = "••••••••"
                self.fields["app_password"].required = False

    def clean_handle(self):
        handle = (self.cleaned_data.get("handle") or "").strip()
        if handle.startswith("@"):
            handle = handle[1:]
        return handle

    def clean_pds_url(self):
        url = (self.cleaned_data.get("pds_url") or "").strip()
        if not url:
            return "https://bsky.social"
        return url.rstrip("/")

    def clean_app_password(self):
        val = self.cleaned_data.get("app_password")
        if (not val or val == "••••••••") and self.instance and self.instance.pk:
            return self.instance.credentials.get("app_password")
        return val.strip() if val else val

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = "bluesky"
        handle = self.cleaned_data.get("handle")
        if not instance.platform_username:
            instance.platform_username = f"@{handle}"
        instance.credentials = {
            "handle": handle,
            "app_password": self.cleaned_data.get("app_password"),
            "pds_url": self.cleaned_data.get("pds_url") or "https://bsky.social",
        }
        if commit:
            instance.save()
        return instance


PROVIDER_FORMS = {
    "telegram": TelegramAccountForm,
    "mastodon": MastodonAccountForm,
    "twitter": TwitterAccountForm,
    "linkedin": LinkedInAccountForm,
    "bluesky": BlueskyAccountForm,
    "postiz": PostizAccountForm,
    "buffer": BufferAccountForm,
}

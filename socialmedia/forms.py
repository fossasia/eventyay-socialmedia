from django import forms
from django.utils.translation import gettext_lazy as _
from eventyay.base.forms import SettingsForm

from .export import DEFAULT_TEMPLATES

MAX_OFFSETS = 10
MAX_OFFSET_VALUE_CFP = 365
MAX_OFFSET_VALUE_SPEAKER = 365
MAX_OFFSET_VALUE_SESSION = 1440
MAX_OFFSET_VALUE_TICKET = 365
MAX_OFFSET_VALUE_SCHEDULE = 90


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

    # ------------------------------------------------------------------
    # Platform toggles
    # ------------------------------------------------------------------
    socialmedia_twitter_enabled = forms.BooleanField(
        label=_("Enable X / Twitter"),
        help_text=_(
            "Generate separate draft posts optimised for X / Twitter (≤280 chars)."
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
    socialmedia_telegram_enabled = forms.BooleanField(
        label=_("Enable Telegram"),
        help_text=_(
            "Generate separate draft posts for Telegram (Markdown formatting)."
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

    # Per-platform template overrides for CFP
    socialmedia_twitter_cfp_template = forms.CharField(
        label=_("X / Twitter — CFP template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Leave blank to use the Twitter-specific default. "
            "Available: {event_name}, {cfp_deadline}, {cfp_link}, {hashtags}"
        ),
    )
    socialmedia_mastodon_cfp_template = forms.CharField(
        label=_("Mastodon — CFP template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Leave blank to use the Mastodon-specific default. "
            "Available: {event_name}, {cfp_deadline}, {cfp_link}, {hashtags}"
        ),
    )
    socialmedia_telegram_cfp_template = forms.CharField(
        label=_("Telegram — CFP template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Leave blank to use the Telegram-specific default (Markdown supported). "
            "Available: {event_name}, {cfp_deadline}, {cfp_link}, {hashtags}"
        ),
    )
    socialmedia_linkedin_cfp_template = forms.CharField(
        label=_("LinkedIn — CFP template"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the LinkedIn-specific default. "
            "Available: {event_name}, {cfp_deadline}, {cfp_link}, {hashtags}"
        ),
    )

    # Per-platform template overrides for Speaker
    socialmedia_twitter_speaker_template = forms.CharField(
        label=_("X / Twitter — Speaker template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Available: {event_name}, {speaker_name}, {speaker_link}, "
            "{talk_title}, {hashtags}"
        ),
    )
    socialmedia_mastodon_speaker_template = forms.CharField(
        label=_("Mastodon — Speaker template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Available: {event_name}, {speaker_name}, {speaker_link}, "
            "{talk_title}, {hashtags}"
        ),
    )
    socialmedia_telegram_speaker_template = forms.CharField(
        label=_("Telegram — Speaker template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Markdown supported. "
            "Available: {event_name}, {speaker_name}, {speaker_link}, "
            "{talk_title}, {hashtags}"
        ),
    )
    socialmedia_linkedin_speaker_template = forms.CharField(
        label=_("LinkedIn — Speaker template"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Available: {event_name}, {speaker_name}, {speaker_link}, "
            "{talk_title}, {hashtags}"
        ),
    )

    # Per-platform template overrides for Session
    socialmedia_twitter_session_template = forms.CharField(
        label=_("X / Twitter — Session template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Available: {event_name}, {talk_title}, {talk_room}, {talk_start_time}, "
            "{speaker_names}, {talk_link}, {hashtags}"
        ),
    )
    socialmedia_mastodon_session_template = forms.CharField(
        label=_("Mastodon — Session template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Available: {event_name}, {talk_title}, {talk_room}, {talk_start_time}, "
            "{speaker_names}, {talk_link}, {hashtags}"
        ),
    )
    socialmedia_telegram_session_template = forms.CharField(
        label=_("Telegram — Session template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Markdown supported. "
            "Available: {event_name}, {talk_title}, {talk_room}, {talk_start_time}, "
            "{speaker_names}, {talk_link}, {hashtags}"
        ),
    )
    socialmedia_linkedin_session_template = forms.CharField(
        label=_("LinkedIn — Session template"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Available: {event_name}, {talk_title}, {talk_room}, {talk_start_time}, "
            "{speaker_names}, {talk_link}, {hashtags}"
        ),
    )

    # Per-platform template overrides for Ticket
    socialmedia_twitter_ticket_template = forms.CharField(
        label=_("X / Twitter — Ticket template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Available: {event_name}, {ticket_name}, {ticket_price}, "
            "{ticket_link}, {hashtags}"
        ),
    )
    socialmedia_mastodon_ticket_template = forms.CharField(
        label=_("Mastodon — Ticket template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Available: {event_name}, {ticket_name}, {ticket_price}, "
            "{ticket_link}, {hashtags}"
        ),
    )
    socialmedia_telegram_ticket_template = forms.CharField(
        label=_("Telegram — Ticket template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Markdown supported. "
            "Available: {event_name}, {ticket_name}, {ticket_price}, "
            "{ticket_link}, {hashtags}"
        ),
    )
    socialmedia_linkedin_ticket_template = forms.CharField(
        label=_("LinkedIn — Ticket template"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Available: {event_name}, {ticket_name}, {ticket_price}, "
            "{ticket_link}, {hashtags}"
        ),
    )

    # Per-platform template overrides for Schedule
    socialmedia_twitter_schedule_template = forms.CharField(
        label=_("X / Twitter — Schedule template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_("Available: {event_name}, {schedule_link}, {hashtags}"),
    )
    socialmedia_mastodon_schedule_template = forms.CharField(
        label=_("Mastodon — Schedule template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_("Available: {event_name}, {schedule_link}, {hashtags}"),
    )
    socialmedia_telegram_schedule_template = forms.CharField(
        label=_("Telegram — Schedule template"),
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        help_text=_(
            "Markdown supported. Available: {event_name}, {schedule_link}, {hashtags}"
        ),
    )
    socialmedia_linkedin_schedule_template = forms.CharField(
        label=_("LinkedIn — Schedule template"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_("Available: {event_name}, {schedule_link}, {hashtags}"),
    )

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

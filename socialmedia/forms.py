from django import forms
from django.utils.translation import gettext_lazy as _

from eventyay.base.forms import SettingsForm

from .export import DEFAULT_TEMPLATES


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
            "Space-separated hashtags appended to every post. E.g. #fossasia #conference"
        ),
        required=False,
        max_length=200,
    )

    # ------------------------------------------------------------------
    # CFP
    # ------------------------------------------------------------------
    socialmedia_cfp_enabled = forms.BooleanField(
        label=_("Enable CFP posts"),
        required=False,
        initial=True,
    )
    socialmedia_cfp_offset = forms.IntegerField(
        label=_("Days before CFP deadline"),
        help_text=_("How many days before the deadline to schedule the announcement."),
        required=False,
        initial=7,
        min_value=0,
    )
    socialmedia_cfp_template = forms.CharField(
        label=_("CFP post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {cfp_deadline}, {cfp_link}, {hashtags}"
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
    socialmedia_speaker_offset = forms.IntegerField(
        label=_("Days before session (speakers)"),
        help_text=_("How many days before the speaker's session to announce them."),
        required=False,
        initial=3,
        min_value=0,
    )
    socialmedia_speaker_template = forms.CharField(
        label=_("Speaker post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {speaker_name}, {speaker_link}, {talk_title}, {hashtags}"
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
    socialmedia_session_offset = forms.IntegerField(
        label=_("Minutes before session"),
        help_text=_(
            "How many minutes before a session starts to schedule the promo post."
        ),
        required=False,
        initial=30,
        min_value=0,
    )
    socialmedia_session_template = forms.CharField(
        label=_("Session post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {talk_title}, {talk_room}, {talk_start_time}, "
            "{speaker_names}, {talk_link}, {hashtags}"
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
    socialmedia_ticket_offset = forms.IntegerField(
        label=_("Days before event (tickets)"),
        help_text=_(
            "How many days before the event starts to post ticket availability."
        ),
        required=False,
        initial=5,
        min_value=0,
    )
    socialmedia_ticket_template = forms.CharField(
        label=_("Ticket post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {ticket_name}, {ticket_price}, {ticket_link}, {hashtags}"
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
    socialmedia_schedule_offset = forms.IntegerField(
        label=_("Days before event (schedule)"),
        help_text=_("How many days before the event to announce the schedule release."),
        required=False,
        initial=2,
        min_value=0,
    )
    socialmedia_schedule_template = forms.CharField(
        label=_("Schedule post template (optional)"),
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text=_(
            "Leave blank to use the default template. "
            "Available: {event_name}, {schedule_link}, {hashtags}"
        ),
    )

    @property
    def default_template_preview(self):
        """Return the baked-in defaults for display in the UI."""

        class _AttrDict(dict):
            """Dict subclass that supports attribute-style access for Django templates."""

            def __getattr__(self, item):
                try:
                    return self[item]
                except KeyError:
                    raise AttributeError(item)

        return _AttrDict(DEFAULT_TEMPLATES)

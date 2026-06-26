import csv
import io
import re
from datetime import timedelta

import pytz
from django.utils.timezone import is_naive, make_aware

try:
    from eventyay.base.models.submission import SubmissionStates
except ImportError:
    SubmissionStates = None

# ---------------------------------------------------------------------------
# Baked-in default templates (used when no custom template is saved)
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES = {
    "cfp": (
        "📢 Submit your proposals for {event_name}! "
        "The deadline is {cfp_deadline}. Apply here: {cfp_link} {hashtags}"
    ),
    "speaker": (
        "🎤 Meet our speaker {speaker_name} at {event_name}! "
        "They'll be presenting '{talk_title}'. Learn more: {speaker_link} {hashtags}"
    ),
    "session": (
        "🗓 Coming up at {event_name}: '{talk_title}' by {speaker_names} "
        "in {talk_room} at {talk_start_time}. Don't miss it! {talk_link} {hashtags}"
    ),
    "ticket": (
        "🎟 Get your {ticket_name} tickets for {event_name}! "
        "Only {ticket_price} — grab yours now: {ticket_link} {hashtags}"
    ),
    "schedule": (
        "📅 The full schedule for {event_name} is now live! "
        "Plan your days: {schedule_link} {hashtags}"
    ),
}

# Human-readable type labels for the UI
TYPE_LABELS = {
    "cfp": "CFP",
    "speaker": "Speaker",
    "session": "Session",
    "ticket": "Ticket",
    "schedule": "Schedule",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def safe_format(template, **kwargs):
    """Replace {placeholders} in template; leave unknown ones as literal text."""

    def replace(match):
        key = match.group(1)
        return str(kwargs.get(key, "{" + key + "}"))

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", replace, template)


def localize(dt, event):
    """Convert a datetime to the event's local timezone."""
    if not dt:
        return None
    tz = pytz.timezone(getattr(event, "timezone", None) or "UTC")
    if is_naive(dt):
        dt = make_aware(dt, pytz.UTC)
    return dt.astimezone(tz)


def event_absolute_url(path, request=None):
    if request:
        return request.build_absolute_uri(path)
    from django.conf import settings as django_settings

    base = getattr(django_settings, "SITE_URL", "").rstrip("/")
    return f"{base}{path}" if base else path


def _get_template(event, key):
    """Return saved custom template or fall back to baked-in default."""
    return event.settings.get(f"socialmedia_{key}_template") or DEFAULT_TEMPLATES[key]


def _get_offset(event, key, default):
    return event.settings.get(f"socialmedia_{key}_offset", default, as_type=int)


# ---------------------------------------------------------------------------
# Core: build the list of posts from live DB data
# ---------------------------------------------------------------------------


def build_posts(event, request=None):
    """
    Return a list of post dicts built from the event's live DB data.
    Each dict has: type, type_label, post_date, post_time, post_text.
    The list is sorted chronologically.
    """
    hashtags = event.settings.get("socialmedia_default_hashtags", "")
    event_link_override = event.settings.get("socialmedia_event_link")
    event_link = event_link_override or event_absolute_url(event.urls.base, request)

    posts = []

    # ---- CFP announcement ------------------------------------------------
    cfp_enabled = event.settings.get("socialmedia_cfp_enabled", True, as_type=bool)
    cfp = getattr(event, "cfp", None)
    if cfp_enabled and cfp and cfp.deadline:
        offset = _get_offset(event, "cfp", 7)
        trigger = localize(cfp.deadline - timedelta(days=offset), event)
        deadline_str = localize(cfp.deadline, event).strftime("%B %-d, %Y")
        cfp_url = event_absolute_url(cfp.urls.public, request)
        text = safe_format(
            _get_template(event, "cfp"),
            event_name=str(event.name),
            cfp_deadline=deadline_str,
            cfp_link=cfp_url,
            hashtags=hashtags,
        )
        ref_date = localize(cfp.deadline, event).strftime("%Y-%m-%d")
        posts.append(
            {
                "id": "cfp",
                "type": "cfp",
                "type_label": TYPE_LABELS["cfp"],
                "post_date": trigger.strftime("%Y-%m-%d"),
                "post_time": trigger.strftime("%H:%M"),
                "post_text": text,
                "default_text": text,
                "reference_date": ref_date,
                "original_post_date": trigger.strftime("%Y-%m-%d"),
                "original_post_time": trigger.strftime("%H:%M"),
            }
        )

    # ---- Schedule release ------------------------------------------------
    schedule_enabled = event.settings.get(
        "socialmedia_schedule_enabled", True, as_type=bool
    )
    if schedule_enabled and getattr(event, "date_from", None):
        offset = _get_offset(event, "schedule", 2)
        trigger = localize(event.date_from - timedelta(days=offset), event)
        schedule_url = event_absolute_url(event.urls.schedule, request)
        text = safe_format(
            _get_template(event, "schedule"),
            event_name=str(event.name),
            schedule_link=schedule_url,
            hashtags=hashtags,
        )
        ref_date = localize(event.date_from, event).strftime("%Y-%m-%d")
        posts.append(
            {
                "id": "schedule",
                "type": "schedule",
                "type_label": TYPE_LABELS["schedule"],
                "post_date": trigger.strftime("%Y-%m-%d"),
                "post_time": trigger.strftime("%H:%M"),
                "post_text": text,
                "default_text": text,
                "reference_date": ref_date,
                "original_post_date": trigger.strftime("%Y-%m-%d"),
                "original_post_time": trigger.strftime("%H:%M"),
            }
        )

    # ---- Ticket announcements --------------------------------------------
    ticket_enabled = event.settings.get(
        "socialmedia_ticket_enabled", True, as_type=bool
    )
    if ticket_enabled and getattr(event, "date_from", None):
        offset = _get_offset(event, "ticket", 5)
        trigger = localize(event.date_from - timedelta(days=offset), event)
        try:
            active_tickets = list(
                event.products.filter(active=True, category__is_addon=False)[:5]
            )
        except Exception:
            active_tickets = []
        for ticket in active_tickets:
            price_str = (
                f"{ticket.default_price} {event.currency}"
                if ticket.default_price
                else "Free"
            )
            text = safe_format(
                _get_template(event, "ticket"),
                event_name=str(event.name),
                ticket_name=str(ticket.name),
                ticket_price=price_str,
                ticket_link=event_link,
                hashtags=hashtags,
            )
            ref_date = localize(event.date_from, event).strftime("%Y-%m-%d")
            posts.append(
                {
                    "id": f"ticket_{ticket.pk}",
                    "type": "ticket",
                    "type_label": TYPE_LABELS["ticket"],
                    "post_date": trigger.strftime("%Y-%m-%d"),
                    "post_time": trigger.strftime("%H:%M"),
                    "post_text": text,
                    "default_text": text,
                    "reference_date": ref_date,
                    "original_post_date": trigger.strftime("%Y-%m-%d"),
                    "original_post_time": trigger.strftime("%H:%M"),
                }
            )

    # ---- Speaker & Session announcements ---------------------------------
    speaker_enabled = event.settings.get(
        "socialmedia_speaker_enabled", True, as_type=bool
    )
    session_enabled = event.settings.get(
        "socialmedia_session_enabled", True, as_type=bool
    )

    if speaker_enabled or session_enabled:
        schedule = getattr(event, "current_schedule", None) or getattr(
            event, "wip_schedule", None
        )
        if schedule:
            filters = {"submission__isnull": False}
            if SubmissionStates:
                filters["submission__state__in"] = [
                    SubmissionStates.CONFIRMED,
                    SubmissionStates.ACCEPTED,
                ]
            talks = list(
                schedule.talks.filter(**filters)
                .select_related("submission", "room")
                .prefetch_related("submission__speakers")
            )

            spk_offset = _get_offset(event, "speaker", 3)
            sess_offset = _get_offset(event, "session", 30)  # minutes

            seen_speakers = set()

            for talk in talks:
                sub = talk.submission
                talk_start = talk.start

                # Speaker post (one per unique speaker)
                if speaker_enabled:
                    base_time = talk_start or getattr(event, "date_from", None)
                    if base_time:
                        trigger = localize(
                            base_time - timedelta(days=spk_offset), event
                        )
                        for speaker in sub.speakers.all():
                            if speaker.pk in seen_speakers:
                                continue
                            seen_speakers.add(speaker.pk)
                            if speaker.code:
                                spk_url = event_absolute_url(
                                    f"{event.urls.base}speakers/{speaker.code}/",
                                    request,
                                )
                            else:
                                spk_url = event_link
                            text = safe_format(
                                _get_template(event, "speaker"),
                                event_name=str(event.name),
                                speaker_name=speaker.get_display_name(),
                                speaker_link=spk_url,
                                talk_title=sub.title,
                                hashtags=hashtags,
                            )
                            ref_date = (
                                localize(base_time, event).strftime("%Y-%m-%d")
                                if base_time
                                else None
                            )
                            posts.append(
                                {
                                    "id": f"speaker_{speaker.pk}_{talk.pk}",
                                    "type": "speaker",
                                    "type_label": TYPE_LABELS["speaker"],
                                    "post_date": trigger.strftime("%Y-%m-%d"),
                                    "post_time": trigger.strftime("%H:%M"),
                                    "post_text": text,
                                    "default_text": text,
                                    "reference_date": ref_date,
                                    "original_post_date": trigger.strftime("%Y-%m-%d"),
                                    "original_post_time": trigger.strftime("%H:%M"),
                                }
                            )

                # Session post
                if session_enabled and talk_start:
                    trigger = localize(
                        talk_start - timedelta(minutes=sess_offset), event
                    )
                    local_start = localize(talk_start, event)
                    names = ", ".join(s.get_display_name() for s in sub.speakers.all())
                    room = talk.room.name if talk.room else "TBA"
                    if sub.code:
                        talk_url = event_absolute_url(
                            f"{event.urls.base}talk/{sub.code}/", request
                        )
                    else:
                        talk_url = event_link
                    text = safe_format(
                        _get_template(event, "session"),
                        event_name=str(event.name),
                        talk_title=sub.title,
                        talk_room=room,
                        talk_start_time=local_start.strftime("%H:%M"),
                        speaker_names=names,
                        talk_link=talk_url,
                        hashtags=hashtags,
                    )
                    ref_date = (
                        localize(talk_start, event).strftime("%Y-%m-%d")
                        if talk_start
                        else None
                    )
                    posts.append(
                        {
                            "id": f"session_{talk.pk}",
                            "type": "session",
                            "type_label": TYPE_LABELS["session"],
                            "post_date": trigger.strftime("%Y-%m-%d"),
                            "post_time": trigger.strftime("%H:%M"),
                            "post_text": text,
                            "default_text": text,
                            "reference_date": ref_date,
                            "original_post_date": trigger.strftime("%Y-%m-%d"),
                            "original_post_time": trigger.strftime("%H:%M"),
                        }
                    )

    # Sort chronologically
    posts.sort(key=lambda p: (p["post_date"], p["post_time"]))
    return posts


# ---------------------------------------------------------------------------
# CSV writer: receives the final post list from the frontend
# ---------------------------------------------------------------------------


def generate_csv_from_posts(posts):
    """
    Accept a list of post dicts (already edited/filtered by the user in the UI)
    and return a CSV string ready for import into social media scheduling tools.
    Only rows where enabled=True are included.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["post_date", "post_time", "post_text", "media_url"])
    for post in posts:
        if post.get("enabled", True):
            writer.writerow(
                [
                    post.get("post_date", ""),
                    post.get("post_time", ""),
                    post.get("post_text", ""),
                    post.get("media_url", ""),
                ]
            )
    return output.getvalue()

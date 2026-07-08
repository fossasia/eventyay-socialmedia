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
    "cfp": {
        "announcement": (
            "📢 Submit your proposals for {event_name}! "
            "The deadline is {cfp_deadline}. Apply here: {cfp_link} {hashtags}"
        ),
        "reminder": (
            "⏰ CFP Closing Soon for {event_name}! Only a few days left "
            "({cfp_deadline}) to submit your proposals: {cfp_link} {hashtags}"
        ),
        "final_call": (
            "🚨 Final Call for Proposals for {event_name}! Submissions close on "
            "{cfp_deadline}. Submit now: {cfp_link} {hashtags}"
        ),
    },
    "speaker": {
        "announcement": (
            "🎤 Meet our speaker {speaker_name} at {event_name}! "
            "They'll be presenting '{talk_title}'. "
            "Learn more: {speaker_link} {hashtags}"
        ),
        "reminder": (
            "🗓 Don't miss {speaker_name} speaking on '{talk_title}' "
            "at {event_name}! Check session details: {speaker_link} {hashtags}"
        ),
        "final_call": (
            "🔥 Spotlight on {speaker_name} presenting '{talk_title}' at "
            "{event_name}! Catch them live: {speaker_link} {hashtags}"
        ),
    },
    "session": {
        "announcement": (
            "🗓 Coming up at {event_name}: '{talk_title}' by {speaker_names} "
            "in {talk_room} at {talk_start_time}. Don't miss it! {talk_link} {hashtags}"
        ),
        "reminder": (
            "⏰ Session starting soon! '{talk_title}' by {speaker_names} "
            "begins at {talk_start_time} in {talk_room}. {talk_link} {hashtags}"
        ),
        "final_call": (
            "🔥 Starting now! '{talk_title}' by {speaker_names} "
            "in {talk_room}. Join live: {talk_link} {hashtags}"
        ),
    },
    "ticket": {
        "announcement": (
            "🎟 Get your {ticket_name} tickets for {event_name}! "
            "Only {ticket_price} — grab yours now: {ticket_link} {hashtags}"
        ),
        "reminder": (
            "⚡ Ticket Reminder: Don't miss out on {ticket_name} for {event_name}! "
            "Get tickets now: {ticket_link} {hashtags}"
        ),
        "final_call": (
            "🔥 Last chance! {ticket_name} tickets for {event_name} "
            "selling fast. Grab yours: {ticket_link} {hashtags}"
        ),
    },
    "schedule": {
        "announcement": (
            "📅 The full schedule for {event_name} is now live! "
            "Plan your days: {schedule_link} {hashtags}"
        ),
        "reminder": (
            "🗓 Check out the schedule for {event_name} and bookmark "
            "your favorite sessions: {schedule_link} {hashtags}"
        ),
    },
}

# ---------------------------------------------------------------------------
# Distance-based template context mapping
# ---------------------------------------------------------------------------
# Maps offset thresholds to template context keys.  For each post type,
# offsets are evaluated against these thresholds (in the type's native unit:
# days for cfp/speaker/ticket/schedule, minutes for session) to pick the
# right template wave.  The first matching threshold wins.
# ---------------------------------------------------------------------------

WAVE_THRESHOLDS = {
    "cfp": [
        (30, "announcement"),
        (3, "reminder"),
        (0, "final_call"),
    ],
    "speaker": [
        (14, "announcement"),
        (3, "reminder"),
        (0, "final_call"),
    ],
    "session": [
        (1440, "announcement"),  # 1440 min = 1 day
        (60, "reminder"),
        (0, "final_call"),
    ],
    "ticket": [
        (14, "announcement"),
        (3, "reminder"),
        (0, "final_call"),
    ],
    "schedule": [
        (7, "announcement"),
        (0, "reminder"),
    ],
}


def resolve_template_context(post_type, offset_value):
    """Return the template context key (announcement/reminder/final_call)
    based on how far out the offset is."""
    thresholds = WAVE_THRESHOLDS.get(post_type, [])
    for threshold, ctx in thresholds:
        if offset_value >= threshold:
            return ctx
    return "announcement"


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


def _get_template(event, key, context="announcement"):
    """Return saved custom template or fall back to baked-in contextual default.

    NOTE: If a custom template is set by the organizer, it overrides all contextual
    waves (announcement, reminder, final_call) with the exact same text, resulting in
    identical copy across different offsets.
    """
    custom = event.settings.get(f"socialmedia_{key}_template")
    if custom:
        return custom
    tpl = DEFAULT_TEMPLATES.get(key, {})
    if isinstance(tpl, dict):
        return tpl.get(context) or tpl.get("announcement") or list(tpl.values())[0]
    return tpl


def _get_template_for_offset(event, key, offset_value):
    """Return the template matching the distance-based wave for this offset."""
    context = resolve_template_context(key, offset_value)
    return _get_template(event, key, context), context


def _get_offset(event, key, default):
    return _get_offsets(event, key, default)[0]


def _get_offsets(event, key, default):
    raw = event.settings.get(f"socialmedia_{key}_offset")
    if raw is None or raw == "":
        return [default]
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, float):
        return [int(raw)]
    val_str = str(raw).strip()
    if not val_str:
        return [default]
    offsets = []
    for part in val_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "." in part:
                offsets.append(int(float(part)))
            else:
                offsets.append(int(part))
        except (ValueError, TypeError):
            pass
    return sorted(set(offsets), reverse=True) if offsets else [default]


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
        cfp_offsets = _get_offsets(event, "cfp", 7)
        deadline_str = localize(cfp.deadline, event).strftime("%B %-d, %Y")
        cfp_url = event_absolute_url(cfp.urls.public, request)
        ref_date = localize(cfp.deadline, event).strftime("%Y-%m-%d")
        for cfp_off in cfp_offsets:
            text, template_ctx = _get_template_for_offset(event, "cfp", cfp_off)
            text = safe_format(
                text,
                event_name=str(event.name),
                cfp_deadline=deadline_str,
                cfp_link=cfp_url,
                hashtags=hashtags,
            )
            trigger = localize(cfp.deadline - timedelta(days=cfp_off), event)
            post_id = "cfp"
            posts.append(
                {
                    "id": post_id,
                    "type": "cfp",
                    "type_label": TYPE_LABELS["cfp"],
                    "post_date": trigger.strftime("%Y-%m-%d"),
                    "post_time": trigger.strftime("%H:%M"),
                    "post_text": text,
                    "default_text": text,
                    "reference_date": ref_date,
                    "original_post_date": trigger.strftime("%Y-%m-%d"),
                    "original_post_time": trigger.strftime("%H:%M"),
                    "event_schedule_display": "N/A",
                    "is_schedule_associated": False,
                    "offset_days": cfp_off,
                    "template_context": template_ctx,
                }
            )

    # ---- Schedule release ------------------------------------------------
    schedule_enabled = event.settings.get(
        "socialmedia_schedule_enabled", True, as_type=bool
    )
    if schedule_enabled and getattr(event, "date_from", None):
        sched_offsets = _get_offsets(event, "schedule", 2)
        schedule_url = event_absolute_url(event.urls.schedule, request)
        ref_date = localize(event.date_from, event).strftime("%Y-%m-%d")
        for sched_off in sched_offsets:
            text, template_ctx = _get_template_for_offset(event, "schedule", sched_off)
            text = safe_format(
                text,
                event_name=str(event.name),
                schedule_link=schedule_url,
                hashtags=hashtags,
            )
            trigger = localize(event.date_from - timedelta(days=sched_off), event)
            post_id = "schedule"
            posts.append(
                {
                    "id": post_id,
                    "type": "schedule",
                    "type_label": TYPE_LABELS["schedule"],
                    "post_date": trigger.strftime("%Y-%m-%d"),
                    "post_time": trigger.strftime("%H:%M"),
                    "post_text": text,
                    "default_text": text,
                    "reference_date": ref_date,
                    "original_post_date": trigger.strftime("%Y-%m-%d"),
                    "original_post_time": trigger.strftime("%H:%M"),
                    "event_schedule_display": "N/A",
                    "is_schedule_associated": False,
                    "offset_days": sched_off,
                    "template_context": template_ctx,
                }
            )

    # ---- Ticket announcements --------------------------------------------
    ticket_enabled = event.settings.get(
        "socialmedia_ticket_enabled", True, as_type=bool
    )
    if ticket_enabled and getattr(event, "date_from", None):
        tkt_offsets = _get_offsets(event, "ticket", 5)
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
            ref_date = localize(event.date_from, event).strftime("%Y-%m-%d")
            for tkt_off in tkt_offsets:
                text, template_ctx = _get_template_for_offset(event, "ticket", tkt_off)
                text = safe_format(
                    text,
                    event_name=str(event.name),
                    ticket_name=str(ticket.name),
                    ticket_price=price_str,
                    ticket_link=event_link,
                    hashtags=hashtags,
                )
                trigger = localize(event.date_from - timedelta(days=tkt_off), event)
                post_id = f"ticket_{ticket.pk}"
                posts.append(
                    {
                        "id": post_id,
                        "type": "ticket",
                        "type_label": TYPE_LABELS["ticket"],
                        "post_date": trigger.strftime("%Y-%m-%d"),
                        "post_time": trigger.strftime("%H:%M"),
                        "post_text": text,
                        "default_text": text,
                        "reference_date": ref_date,
                        "original_post_date": trigger.strftime("%Y-%m-%d"),
                        "original_post_time": trigger.strftime("%H:%M"),
                        "event_schedule_display": "N/A",
                        "is_schedule_associated": False,
                        "offset_days": tkt_off,
                        "template_context": template_ctx,
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
        submissions_mgr = getattr(event, "submissions", None)
        if submissions_mgr:
            filters = {}
            if SubmissionStates:
                filters["state"] = SubmissionStates.CONFIRMED
            confirmed_subs = list(
                submissions_mgr.filter(**filters).prefetch_related("speakers")
            )

            schedule = getattr(event, "current_schedule", None)
            talks_by_sub = {}
            if schedule:
                talk_qs = schedule.talks.filter(
                    submission__in=confirmed_subs
                ).select_related("submission", "room")
                for talk in talk_qs:
                    talks_by_sub[talk.submission_id] = talk

            spk_offsets = _get_offsets(event, "speaker", 3)
            sess_offsets = _get_offsets(event, "session", 30)  # minutes

            seen_speaker_offsets = set()

            for sub in confirmed_subs:
                talk = talks_by_sub.get(sub.pk)
                talk_start = talk.start if talk else None

                if talk_start:
                    local_start = localize(talk_start, event)
                    sched_display = local_start.strftime("%b %d, %Y %H:%M")
                else:
                    sched_display = "Unscheduled"

                # Speaker post (one per unique speaker per offset)
                if speaker_enabled:
                    base_time = talk_start or getattr(event, "date_from", None)
                    if base_time:
                        for spk_off in spk_offsets:
                            trigger = localize(
                                base_time - timedelta(days=spk_off), event
                            )
                            for speaker in sub.speakers.all():
                                if (speaker.pk, spk_off) in seen_speaker_offsets:
                                    continue
                                seen_speaker_offsets.add((speaker.pk, spk_off))
                                if speaker.code:
                                    spk_url = event_absolute_url(
                                        f"{event.urls.base}speakers/{speaker.code}/",
                                        request,
                                    )
                                else:
                                    spk_url = event_link
                                text, template_ctx = _get_template_for_offset(
                                    event, "speaker", spk_off
                                )
                                text = safe_format(
                                    text,
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
                                talk_pk = talk.pk if talk else sub.pk
                                post_id = f"speaker_{speaker.pk}_{talk_pk}"
                                posts.append(
                                    {
                                        "id": post_id,
                                        "type": "speaker",
                                        "type_label": TYPE_LABELS["speaker"],
                                        "post_date": trigger.strftime("%Y-%m-%d"),
                                        "post_time": trigger.strftime("%H:%M"),
                                        "post_text": text,
                                        "default_text": text,
                                        "reference_date": ref_date,
                                        "original_post_date": trigger.strftime(
                                            "%Y-%m-%d"
                                        ),
                                        "original_post_time": trigger.strftime("%H:%M"),
                                        "event_schedule_display": sched_display,
                                        "is_schedule_associated": True,
                                        "offset_days": spk_off,
                                        "template_context": template_ctx,
                                    }
                                )

                # Session post
                if session_enabled and talk_start:
                    names = ", ".join(
                        s.get_display_name() for s in sub.speakers.all()
                    )
                    room = talk.room.name if (talk and talk.room) else "TBA"
                    if sub.code:
                        talk_url = event_absolute_url(
                            f"{event.urls.base}talk/{sub.code}/", request
                        )
                    else:
                        talk_url = event_link
                    ref_date = localize(talk_start, event).strftime("%Y-%m-%d")
                    talk_pk = talk.pk if talk else sub.pk
                    for sess_off in sess_offsets:
                        trigger = localize(
                            talk_start - timedelta(minutes=sess_off), event
                        )
                        text, template_ctx = _get_template_for_offset(
                            event, "session", sess_off
                        )
                        text = safe_format(
                            text,
                            event_name=str(event.name),
                            talk_title=sub.title,
                            talk_room=room,
                            talk_start_time=(
                                localize(talk_start, event).strftime("%H:%M")
                                if talk_start
                                else "TBA"
                            ),
                            speaker_names=names,
                            talk_link=talk_url,
                            hashtags=hashtags,
                        )
                        post_id = f"session_{talk_pk}"
                        posts.append(
                            {
                                "id": post_id,
                                "type": "session",
                                "type_label": TYPE_LABELS["session"],
                                "post_date": trigger.strftime("%Y-%m-%d"),
                                "post_time": trigger.strftime("%H:%M"),
                                "post_text": text,
                                "default_text": text,
                                "reference_date": ref_date,
                                "original_post_date": trigger.strftime("%Y-%m-%d"),
                                "original_post_time": trigger.strftime("%H:%M"),
                                "event_schedule_display": sched_display,
                                "is_schedule_associated": True,
                                "offset_days": sess_off,
                                "template_context": template_ctx,
                            }
                        )

    # Sort chronologically
    posts.sort(key=lambda p: (p["post_date"], p["post_time"]))
    return posts


def sync_posts_to_db(event, request=None):
    """Sync built posts into SocialMediaPost database records."""
    from datetime import datetime

    from .models import SocialMediaPost, SocialMediaPostStatus

    posts = build_posts(event, request)
    tz = pytz.timezone(getattr(event, "timezone", None) or "UTC")

    generated_keys = set()
    for p in posts:
        generated_keys.add((str(p["id"]), p.get("offset_days", 0)))
        dt_str = f"{p['post_date']} {p['post_time']}"
        try:
            naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            scheduled_at = tz.localize(naive_dt)
        except Exception:
            continue

        offset_val = p.get("offset_days", 0)
        db_post, created = SocialMediaPost.objects.get_or_create(
            event=event,
            post_type=p["type"],
            entity_id=str(p["id"]),
            offset_days=offset_val,
            defaults={
                "scheduled_at": scheduled_at,
                "post_text": p["post_text"],
                "template_context": p.get("template_context", "announcement"),
                "status": SocialMediaPostStatus.SCHEDULED,
            },
        )
        if not created and not db_post.is_pinned:
            db_post.scheduled_at = scheduled_at
            db_post.post_text = p["post_text"]
            db_post.template_context = p.get("template_context", "announcement")
            db_post.save()

    # Clean up obsolete non-pinned, non-custom posts that are no longer generated.
    # A post is obsolete when its (entity_id, offset_days) pair is no longer in the
    # generated set (e.g. an offset was removed from settings, or a talk was removed).
    for db_post in SocialMediaPost.objects.filter(
        event=event,
        is_pinned=False,
        status__in=[
            SocialMediaPostStatus.DRAFT,
            SocialMediaPostStatus.SCHEDULED,
            SocialMediaPostStatus.EXCLUDED,
        ],
    ).exclude(post_type="custom"):
        if (db_post.entity_id, db_post.offset_days) not in generated_keys:
            db_post.delete()

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

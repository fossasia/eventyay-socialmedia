from django.conf import settings
from django.db import transaction
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import resolve, reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled
from eventyay.base.models import Team
from eventyay.common.signals import periodic_task
from eventyay.control.signals import (
    event_dashboard_components,
    nav_event_common,
    nav_global,
    nav_organizer,
)

from .models import SocialMediaAccount, SocialMediaPost, SocialMediaPostStatus

HAS_SOCIAL_MEDIA_PERM = hasattr(Team, "can_manage_social_media")
DIRECT_PUBLISH_PROVIDERS = ["telegram", "mastodon"]
SCHEDULER_PROVIDERS = ["postiz", "buffer"]

ORGANIZER_PERMISSION = (
    ("can_change_organizer_settings", "can_manage_social_media")
    if HAS_SOCIAL_MEDIA_PERM
    else "can_change_organizer_settings"
)

EVENT_PERMISSION = (
    ("can_change_event_settings", "can_manage_social_media")
    if HAS_SOCIAL_MEDIA_PERM
    else "can_change_event_settings"
)


@receiver(nav_organizer, dispatch_uid="socialmedia_nav_organizer")
def control_nav_organizer_socialmedia(sender, request=None, **kwargs):
    if not request or not request.user.is_authenticated:
        return []
    if not request.user.has_organizer_permission(
        sender,
        ORGANIZER_PERMISSION,
        request=request,
    ):
        return []
    url = resolve(request.path_info)
    return [
        {
            "label": str(_("Social Media Accounts")),
            "url": reverse(
                "plugins:socialmedia:organizer_accounts",
                kwargs={
                    "organizer": sender.slug,
                },
            ),
            "icon": "share-alt",
            "active": (
                url.namespace == "plugins:socialmedia"
                and url.url_name.startswith("organizer_account")
            ),
        }
    ]


@receiver(nav_global, dispatch_uid="socialmedia_nav")
def control_nav_socialmedia(sender, request=None, **kwargs):
    return []


@receiver(nav_event_common, dispatch_uid="socialmedia_nav_event_common")
def control_nav_event_common_socialmedia(sender, request=None, **kwargs):
    if not request or not request.user.is_authenticated:
        return []
    if not request.user.has_event_permission(
        sender.organizer,
        sender,
        EVENT_PERMISSION,
        request=request,
    ):
        return []
    url = resolve(request.path_info)
    return [
        {
            "label": str(_("Social Media")),
            "url": reverse(
                "plugins:socialmedia:index",
                kwargs={
                    "organizer": sender.organizer.slug,
                    "event": sender.slug,
                },
            ),
            "icon": "share-alt",
            "active": (
                url.namespace == "plugins:socialmedia" and url.url_name == "index"
            ),
        }
    ]


@receiver(event_dashboard_components, dispatch_uid="socialmedia_dashboard_components")
def control_dashboard_socialmedia(sender, request=None, **kwargs):
    return render_to_string(
        "socialmedia/dashboard_component.html",
        {"request": request},
        request=request,
    )


def claim_post_for_publishing(post_pk, provider_name):
    """Atomically claim a scheduled or failed post for publishing.

    Transitions status to EXPORTED while holding select_for_update row lock,
    releasing the lock immediately upon commit before HTTP network calls.
    Returns (claimed_post, account) or (None, None) if unavailable.
    """
    with transaction.atomic():
        locked_post = (
            SocialMediaPost.objects.filter(
                pk=post_pk,
                status__in=[
                    SocialMediaPostStatus.SCHEDULED,
                    SocialMediaPostStatus.FAILED,
                ],
            )
            .select_for_update(skip_locked=True)
            .first()
        )
        if not locked_post:
            return None, None

        account = SocialMediaAccount.objects.filter(
            organizer=locked_post.event.organizer,
            provider=provider_name,
            is_active=True,
        ).first()

        if not account:
            locked_post.status = SocialMediaPostStatus.FAILED
            locked_post.error_message = (
                f"No active {provider_name} account found for organizer."
            )
            locked_post.save(update_fields=["status", "error_message"])
            return None, None

        locked_post.status = SocialMediaPostStatus.EXPORTED
        locked_post.error_message = ""
        locked_post.save(update_fields=["status", "error_message"])
        return locked_post, account


@receiver(periodic_task, dispatch_uid="socialmedia_publish_scheduled_posts")
@scopes_disabled()
def publish_scheduled_posts(sender, **kwargs):
    """Periodic task dispatcher to publish scheduled social media posts
    for direct integrations (Telegram, Mastodon).
    Dispatches execution to dedicated Celery tasks off the main beat worker.
    """
    from .tasks import publish_single_post

    due_posts = SocialMediaPost.objects.filter(
        status=SocialMediaPostStatus.SCHEDULED,
        is_pinned=True,
        scheduled_at__lte=now(),
    ).order_by("scheduled_at", "pk")

    for post in due_posts:
        entity_id = post.entity_id or ""
        provider_names = []
        if any(entity_id.endswith(f"_{prov}") for prov in SCHEDULER_PROVIDERS):
            continue

        for prov in DIRECT_PUBLISH_PROVIDERS:
            if entity_id.endswith(f"_{prov}"):
                provider_names = [prov]
                break

        if not provider_names:
            # Fallback: check which direct integrations are active for this organizer
            active_provs = list(
                SocialMediaAccount.objects.filter(
                    organizer=post.event.organizer,
                    provider__in=DIRECT_PUBLISH_PROVIDERS,
                    is_active=True,
                )
                .values_list("provider", flat=True)
                .distinct()
            )
            provider_names = active_provs

        for provider_name in provider_names:
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False) or getattr(
                settings, "CELERY_ALWAYS_EAGER", False
            ):
                publish_single_post(post.pk, provider_name)
            else:
                publish_single_post.apply_async(args=[post.pk, provider_name])

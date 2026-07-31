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
from .providers.registry import get_provider

HAS_SOCIAL_MEDIA_PERM = hasattr(Team, "can_manage_social_media")

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


@receiver(periodic_task, dispatch_uid="socialmedia_periodic_publishing")
@scopes_disabled()
def publish_scheduled_posts(sender, **kwargs):
    """Periodic task to publish scheduled social media posts
    for direct integrations (Telegram, Mastodon).
    """
    due_posts = SocialMediaPost.objects.filter(
        status=SocialMediaPostStatus.SCHEDULED,
        scheduled_at__lte=now(),
    ).order_by("scheduled_at", "pk")

    for post in due_posts:
        entity_id = post.entity_id or ""
        provider_name = None
        for prov in ["telegram", "mastodon"]:
            if entity_id.endswith(f"_{prov}"):
                provider_name = prov
                break

        if not provider_name:
            continue

        account = None
        target_post = None

        with transaction.atomic():
            locked_post = (
                SocialMediaPost.objects.filter(
                    pk=post.pk, status=SocialMediaPostStatus.SCHEDULED
                )
                .select_for_update(skip_locked=True)
                .first()
            )
            if not locked_post:
                continue

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
                continue

            # Mark as claimed before releasing DB lock to prevent race conditions
            locked_post.status = SocialMediaPostStatus.EXPORTED
            locked_post.save(update_fields=["status"])
            target_post = locked_post

        # Perform HTTP network publish request OUTSIDE of atomic transaction lock block
        try:
            provider = get_provider(account)
            media = [target_post.media_url] if target_post.media_url else None
            provider.publish_post(text=target_post.post_text, media=media)
            target_post.status = SocialMediaPostStatus.PUBLISHED
            target_post.error_message = ""
            target_post.save(update_fields=["status", "error_message"])
        except Exception as e:
            target_post.status = SocialMediaPostStatus.FAILED
            target_post.error_message = str(e)
            target_post.save(update_fields=["status", "error_message"])

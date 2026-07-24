from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Team
from eventyay.control.signals import (
    event_dashboard_components,
    nav_event_common,
    nav_global,
    nav_organizer,
)

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
            "label": _("Social Media Accounts"),
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
            "label": _("Social Media"),
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

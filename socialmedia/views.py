from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render

from eventyay.eventyay_common.navigation import get_event_navigation


def index(request, organizer, event):
    # Event/organizer are pre-resolved and attached to the request by core PermissionMiddleware.

    # Check specific dashboard edit permissions
    if not request.user.has_event_permission(
        request.organizer,
        request.event,
        "can_change_event_settings",
        request=request,
    ):
        raise PermissionDenied()

    # Check if the plugin is active for the event
    if "socialmedia" not in request.event.get_plugins():
        raise Http404("Social Media plugin is not enabled for this event.")

    # Populate navigation items for the sidebar
    nav_items = get_event_navigation(request, request.event)

    return render(
        request,
        "socialmedia/index.html",
        {
            "event": request.event,
            "nav_items": nav_items,
        },
    )

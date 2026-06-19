from django.urls import path

from eventyay.common.urls import OrganizerSlugConverter  # noqa: F401

from . import views

app_name = "socialmedia"

urlpatterns = [
    path(
        "social/event/<orgslug:organizer>/<slug:event>/",
        views.SocialMediaSettingsView.as_view(),
        name="index",
    ),
    path(
        "social/event/<orgslug:organizer>/<slug:event>/preview/",
        views.preview_posts,
        name="preview",
    ),
    path(
        "social/event/<orgslug:organizer>/<slug:event>/export/",
        views.export_csv,
        name="export",
    ),
]

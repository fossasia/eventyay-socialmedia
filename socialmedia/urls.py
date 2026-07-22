from django.urls import path
from eventyay.common.urls import OrganizerSlugConverter  # noqa: F401

from . import views

app_name = "socialmedia"

urlpatterns = [
    # ── Main landing → Posts table ────────────────────────────────────────────
    path(
        "social/event/<orgslug:organizer>/<slug:event>/",
        views.SocialMediaSettingsView.as_view(),
        name="index",  # kept for backwards compat (nav signal, old links)
    ),
    path(
        "social/event/<orgslug:organizer>/<slug:event>/posts/",
        views.SocialMediaSettingsView.as_view(),
        name="posts",
    ),

    # ── Settings form ─────────────────────────────────────────────────────────
    path(
        "social/event/<orgslug:organizer>/<slug:event>/settings/",
        views.SocialMediaPostSettingsView.as_view(),
        name="plugin_settings",
    ),

    # ── Publishing log ────────────────────────────────────────────────────────
    path(
        "social/event/<orgslug:organizer>/<slug:event>/log/",
        views.PublishingLogView.as_view(),
        name="log",
    ),

    # ── AJAX endpoints ────────────────────────────────────────────────────────
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
    path(
        "social/event/<orgslug:organizer>/<slug:event>/update/",
        views.update_post,
        name="update",
    ),
    path(
        "social/event/<orgslug:organizer>/<slug:event>/sync/",
        views.sync_to_schedulers,
        name="sync",
    ),
    path(
        "social/event/<orgslug:organizer>/<slug:event>/publish-now/",
        views.publish_post_now,
        name="publish_now",
    ),

    # ── Organizer-level account management ────────────────────────────────────
    path(
        "social/organizer/<orgslug:organizer>/accounts/",
        views.OrganizerAccountsListView.as_view(),
        name="organizer_accounts",
    ),
    path(
        "social/organizer/<orgslug:organizer>/accounts/add/",
        views.OrganizerAccountCreateView.as_view(),
        name="organizer_account_add",
    ),
    path(
        "social/organizer/<orgslug:organizer>/accounts/<int:pk>/edit/",
        views.OrganizerAccountUpdateView.as_view(),
        name="organizer_account_edit",
    ),
    path(
        "social/organizer/<orgslug:organizer>/accounts/<int:pk>/delete/",
        views.OrganizerAccountDeleteView.as_view(),
        name="organizer_account_delete",
    ),
    path(
        "social/organizer/<orgslug:organizer>/accounts/<int:pk>/test/",
        views.test_connection,
        name="organizer_account_test",
    ),
]

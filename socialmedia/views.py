import json
import logging
from datetime import datetime

import pytz
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView
from eventyay.base.models import Team
from eventyay.control.permissions import OrganizerPermissionRequiredMixin
from eventyay.control.views.event import DecoupleMixin
from eventyay.control.views.organizer_views.organizer_detail_view_mixin import (
    OrganizerDetailViewMixin,
)

from .export import build_posts, generate_csv_from_posts, sync_posts_to_db
from .forms import PROVIDER_FORMS, SocialMediaSettingsForm
from .models import SocialMediaAccount, SocialMediaPost, SocialMediaPostStatus

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

logger = logging.getLogger(__name__)


def _check_plugin_active(request):
    if "socialmedia" not in request.event.get_plugins():
        raise Http404("Social Media plugin is not enabled for this event.")


def _check_permission(request):
    if not request.user.has_event_permission(
        request.organizer,
        request.event,
        EVENT_PERMISSION,
        request=request,
    ):
        raise PermissionDenied()


class SocialMediaSettingsView(DecoupleMixin, FormView):
    """
    Plugin settings + live post preview page.

    Deliberately does NOT inherit from EventSettingsViewMixin (control panel)
    so that the common-sidebar layout is preserved.
    """

    form_class = SocialMediaSettingsForm
    template_name = "socialmedia/settings.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        _check_plugin_active(request)
        _check_permission(request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # SettingsForm expects obj= to know which event settings to read/write.
        kwargs["obj"] = self.request.event
        return kwargs

    def get_success_url(self):
        return reverse(
            "plugins:socialmedia:index",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["event"] = self.request.event
        ctx["preview_url"] = reverse(
            "plugins:socialmedia:preview",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )
        ctx["export_url"] = reverse(
            "plugins:socialmedia:export",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )
        ctx["update_url"] = reverse(
            "plugins:socialmedia:update",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        self._save_decoupled(form)
        form.save()
        if form.has_changed():
            self.request.event.log_action(
                "eventyay.event.settings",
                user=self.request.user,
                data={k: form.cleaned_data.get(k) for k in form.changed_data},
            )
        sync_posts_to_db(self.request.event, self.request)
        messages.success(self.request, _("Your changes have been saved."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            _("We could not save your changes. See below for details."),
        )
        return super().form_invalid(form)


def preview_posts(request, organizer, event):
    """AJAX GET — returns JSON list of generated posts merged with DB state.

    Syncs generated schedule posts to DB via sync_posts_to_db() and returns
    full preview metadata (status badges, media URLs, custom schedule text).
    """
    _check_permission(request)
    _check_plugin_active(request)
    try:
        sync_posts_to_db(request.event, request)
        raw_posts = build_posts(request.event, request)
        db_posts = {
            (p.post_type, p.entity_id, p.offset_days): p
            for p in SocialMediaPost.objects.filter(event=request.event)
        }
        posts = []
        for p in raw_posts:
            entity_id = str(p["id"])
            offset = p.get("offset_days", 0)
            db_p = db_posts.get((p["type"], entity_id, offset))
            if db_p:
                p["db_id"] = db_p.pk
                p["status"] = db_p.status
                p["is_pinned"] = db_p.is_pinned
                p["post_text"] = db_p.post_text
                p["media_url"] = db_p.media_url or p.get("media_url") or ""
                p["error_message"] = db_p.error_message or ""

                tz = pytz.timezone(getattr(request.event, "timezone", None) or "UTC")
                local_dt = db_p.scheduled_at.astimezone(tz)
                p["post_date"] = local_dt.strftime("%Y-%m-%d")
                p["post_time"] = local_dt.strftime("%H:%M")
            else:
                p["status"] = "scheduled"
                p["error_message"] = ""
                p["media_url"] = p.get("media_url") or ""
            posts.append(p)
    except Exception:  # pragma: no cover
        return JsonResponse({"error": "Internal server error"}, status=500)
    return JsonResponse({"posts": posts})


@require_POST
def update_post(request, organizer, event):
    """AJAX POST — update social media post copy or scheduled date/time/status."""
    _check_permission(request)
    _check_plugin_active(request)
    try:
        data = json.loads(request.body)
        post_id = data.get("id")
        db_id = data.get("db_id")
        post_text = data.get("post_text")
        post_date = data.get("post_date")
        post_time = data.get("post_time")
        status = data.get("status")

        is_pinned = data.get("is_pinned")

        post_type = data.get("post_type")

        db_post = None
        if db_id:
            db_post = SocialMediaPost.objects.filter(
                pk=db_id, event=request.event
            ).first()
        if not db_post and post_id:
            lookup_filters = {"entity_id": str(post_id), "event": request.event}
            if post_type:
                lookup_filters["post_type"] = post_type
            db_post = SocialMediaPost.objects.filter(**lookup_filters).first()

        if not db_post:
            return JsonResponse({"error": "Post not found"}, status=404)

        if post_text is not None:
            db_post.post_text = post_text
        if status is not None:
            if status not in SocialMediaPostStatus.values:
                return JsonResponse({"error": "Invalid status"}, status=400)
            db_post.status = status
        if post_date and post_time:
            tz = pytz.timezone(getattr(request.event, "timezone", None) or "UTC")
            dt_str = f"{post_date} {post_time}"
            naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            db_post.scheduled_at = tz.localize(naive_dt)

        if is_pinned is not None:
            db_post.is_pinned = is_pinned
        elif post_text is not None or (post_date and post_time):
            # Auto-pin when the organizer explicitly edits text or reschedules a post
            db_post.is_pinned = True
        db_post.save()
        return JsonResponse(
            {"status": "ok", "db_id": db_post.pk, "is_pinned": db_post.is_pinned}
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception:
        return JsonResponse({"error": "Internal server error"}, status=500)


@require_POST
def export_csv(request, organizer, event):
    """POST — receives final post list from frontend, returns CSV download."""
    _check_permission(request)
    _check_plugin_active(request)

    try:
        body = json.loads(request.body)
        posts = body.get("posts", [])
        export_format = body.get("format", "generic")
    except (json.JSONDecodeError, KeyError):
        return HttpResponse("Invalid request body.", status=400)

    csv_data = generate_csv_from_posts(posts, export_format)
    filename = f"{request.event.slug}_socialmedia_posts.csv"
    response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class OrganizerAccountsListView(
    OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, ListView
):
    model = SocialMediaAccount
    template_name = "socialmedia/organizer/accounts.html"
    context_object_name = "accounts"
    permission = ORGANIZER_PERMISSION

    def get_queryset(self):
        return SocialMediaAccount.objects.filter(organizer=self.request.organizer)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        event_slug = self.request.GET.get("event")
        if event_slug:
            ctx["back_to_event_url"] = reverse(
                "plugins:socialmedia:index",
                kwargs={
                    "organizer": self.request.organizer.slug,
                    "event": event_slug,
                },
            )
        return ctx


class OrganizerAccountCreateView(
    OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, CreateView
):
    model = SocialMediaAccount
    template_name = "socialmedia/organizer/account_form.html"
    permission = ORGANIZER_PERMISSION

    def dispatch(self, request, *args, **kwargs):
        self.provider = request.GET.get("provider")
        if not self.provider or self.provider not in PROVIDER_FORMS:
            messages.error(request, _("Please select a provider first."))
            return redirect(
                reverse(
                    "plugins:socialmedia:organizer_accounts",
                    kwargs={"organizer": request.organizer.slug},
                )
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .providers.registry import get_provider_class

        try:
            provider_cls = get_provider_class(self.provider)
            ctx["setup_instructions"] = provider_cls.get_setup_instructions()
        except ValueError:
            pass
        return ctx

    def get_form_class(self):
        return PROVIDER_FORMS[self.provider]

    def form_valid(self, form):
        form.instance.organizer = self.request.organizer
        self._validate_connection(form)
        response = super().form_valid(form)
        messages.success(self.request, _("Account successfully connected."))
        return response

    def _validate_connection(self, form):
        from .providers.registry import get_provider

        try:
            account = form.save(commit=False)
            account.organizer = self.request.organizer
            provider = get_provider(account)
            if not provider.validate_credentials():
                raise Exception("Credentials validation returned False.")
        except Exception as e:
            logger.warning(f"Connection verification failed during save: {e}")
            messages.warning(
                self.request,
                _(
                    "Credentials could not be verified. "
                    "The account was saved but may not work."
                ),
            )

    def get_success_url(self):
        url = reverse(
            "plugins:socialmedia:organizer_accounts",
            kwargs={"organizer": self.request.organizer.slug},
        )
        event_slug = self.request.GET.get("event")
        if event_slug:
            url = f"{url}?event={event_slug}"
        return url


class OrganizerAccountUpdateView(
    OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, UpdateView
):
    model = SocialMediaAccount
    template_name = "socialmedia/organizer/account_form.html"
    permission = ORGANIZER_PERMISSION

    def get_object(self, queryset=None):
        return super(OrganizerDetailViewMixin, self).get_object(queryset)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        provider = self.get_object().provider
        from .providers.registry import get_provider_class

        try:
            provider_cls = get_provider_class(provider)
            ctx["setup_instructions"] = provider_cls.get_setup_instructions()
        except ValueError:
            pass
        return ctx

    def get_queryset(self):
        return SocialMediaAccount.objects.filter(organizer=self.request.organizer)

    def get_form_class(self):
        provider = self.get_object().provider
        return PROVIDER_FORMS.get(provider)

    def form_valid(self, form):
        self._validate_connection(form)
        response = super().form_valid(form)
        messages.success(self.request, _("Account settings updated."))
        return response

    def _validate_connection(self, form):
        from .providers.registry import get_provider

        try:
            account = form.save(commit=False)
            account.organizer = self.request.organizer
            provider = get_provider(account)
            if not provider.validate_credentials():
                raise Exception("Credentials validation returned False.")
        except Exception as e:
            logger.warning(f"Connection verification failed during save: {e}")
            messages.warning(
                self.request,
                _(
                    "Credentials could not be verified. "
                    "The account was saved but may not work."
                ),
            )

    def get_success_url(self):
        url = reverse(
            "plugins:socialmedia:organizer_accounts",
            kwargs={"organizer": self.request.organizer.slug},
        )
        event_slug = self.request.GET.get("event")
        if event_slug:
            url = f"{url}?event={event_slug}"
        return url


class OrganizerAccountDeleteView(
    OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, DeleteView
):
    model = SocialMediaAccount
    template_name = "socialmedia/organizer/account_delete.html"
    permission = ORGANIZER_PERMISSION

    def get_object(self, queryset=None):
        return super(OrganizerDetailViewMixin, self).get_object(queryset)

    def get_queryset(self):
        return SocialMediaAccount.objects.filter(organizer=self.request.organizer)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        account = self.get_object()
        events = self.request.organizer.events.all()

        active_posts = SocialMediaPost.objects.filter(
            event__in=events,
            status=SocialMediaPostStatus.SCHEDULED,
            scheduled_at__gt=timezone.now(),
        )

        # Note: Since SocialMediaPost rows do not have a foreign key to a
        # specific SocialMediaAccount, we filter by the provider type suffix
        # on the entity_id (e.g. "_telegram") or general/aggregator posts.
        if account.provider in ["postiz", "buffer"]:
            # Aggregator integrations sync general scheduled posts (not
            # specific to direct platforms). We exclude posts that are
            # targeted to direct platforms (telegram, mastodon, etc.).
            direct_platforms = ["telegram", "mastodon", "twitter", "linkedin"]
            for p in direct_platforms:
                active_posts = active_posts.exclude(entity_id__endswith=f"_{p}")
            has_active = active_posts.exists()
            count = active_posts.count()
        else:
            has_active = active_posts.filter(
                entity_id__endswith=f"_{account.provider}"
            ).exists()
            count = active_posts.filter(
                entity_id__endswith=f"_{account.provider}"
            ).count()

        ctx["has_active_posts"] = has_active
        ctx["active_posts_count"] = count
        return ctx

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        messages.success(self.request, _("Account successfully disconnected."))
        return response

    def get_success_url(self):
        url = reverse(
            "plugins:socialmedia:organizer_accounts",
            kwargs={"organizer": self.request.organizer.slug},
        )
        event_slug = self.request.GET.get("event")
        if event_slug:
            url = f"{url}?event={event_slug}"
        return url


@require_POST
def test_connection(request, organizer, pk):
    """AJAX POST — send a test message to verify the connection works."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required."},
            status=403,
        )
    if not request.user.has_organizer_permission(
        request.organizer,
        ORGANIZER_PERMISSION,
        request=request,
    ):
        return JsonResponse(
            {"success": False, "message": "Permission denied."},
            status=403,
        )

    account = SocialMediaAccount.objects.filter(
        organizer=request.organizer, pk=pk
    ).first()
    if not account:
        return JsonResponse(
            {"success": False, "message": "Account not found."},
            status=404,
        )

    try:
        from .providers.registry import get_provider

        provider = get_provider(account)
        result = provider.send_test_message()
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_POST
def sync_to_schedulers(request, organizer, event):
    """AJAX POST — trigger synchronization of active scheduled posts
    to Postiz or Buffer scheduler accounts.
    """
    _check_permission(request)
    _check_plugin_active(request)
    try:
        scheduler_accounts = SocialMediaAccount.objects.filter(
            organizer=request.organizer,
            provider__in=["postiz", "buffer"],
            is_active=True,
        )
        if not scheduler_accounts.exists():
            return JsonResponse(
                {
                    "success": False,
                    "message": _("No active scheduler accounts connected."),
                },
                status=400,
            )

        posts_to_sync = SocialMediaPost.objects.filter(
            event=request.event,
            status=SocialMediaPostStatus.SCHEDULED,
            scheduled_at__gt=timezone.now(),
        )
        direct_platforms = ["telegram", "mastodon", "twitter", "linkedin"]
        for p in direct_platforms:
            posts_to_sync = posts_to_sync.exclude(entity_id__endswith=f"_{p}")

        if not posts_to_sync.exists():
            return JsonResponse(
                {"success": True, "message": _("No scheduled posts found to sync.")}
            )

        from .providers.registry import get_provider

        synced_count = 0
        errors = []

        for account in scheduler_accounts:
            try:
                provider = get_provider(account)
                provider.sync_campaign(list(posts_to_sync))
                synced_count += 1
            except Exception as e:
                errors.append(f"{account.provider}: {str(e)}")

        if synced_count > 0:
            posts_to_sync.update(status=SocialMediaPostStatus.EXPORTED)

        if errors:
            succ_msg = (
                f" ({synced_count}/{len(scheduler_accounts)} succeeded)"
                if synced_count > 0
                else ""
            )
            err_str = ", ".join(errors)
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Synchronization partially failed{succ_msg}: {err_str}",
                },
                status=500,
            )

        return JsonResponse(
            {
                "success": True,
                "message": (
                    f"Successfully synchronized posts to {synced_count} "
                    "scheduler platform(s)."
                ),
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_POST
def publish_post_now(request, organizer, event):
    """AJAX POST — manual retry or immediate publishing for a specific post."""
    _check_permission(request)
    _check_plugin_active(request)
    try:
        data = json.loads(request.body)
        db_id = data.get("db_id")
        post_id = data.get("post_id")

        db_post = None
        if db_id:
            db_post = SocialMediaPost.objects.filter(
                pk=db_id, event=request.event
            ).first()
        if not db_post and post_id:
            db_post = SocialMediaPost.objects.filter(
                entity_id=str(post_id), event=request.event
            ).first()

        if not db_post:
            return JsonResponse(
                {"success": False, "message": _("Post not found.")}, status=404
            )

        with transaction.atomic():
            locked_post = (
                SocialMediaPost.objects.filter(pk=db_post.pk)
                .select_for_update(skip_locked=True)
                .first()
            )
            if not locked_post:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _(
                            "Post is currently being processed by another worker."
                        ),
                    },
                    status=409,
                )
            db_post = locked_post
            db_post.status = SocialMediaPostStatus.EXPORTED
            db_post.error_message = ""
            db_post.save(update_fields=["status", "error_message"])

        from .providers.registry import get_provider

        entity_id = db_post.entity_id or ""
        provider_name = None
        for prov in ["telegram", "mastodon", "postiz", "buffer"]:
            if entity_id.endswith(f"_{prov}"):
                provider_name = prov
                break

        active_accounts = []
        if provider_name:
            account = SocialMediaAccount.objects.filter(
                organizer=request.organizer,
                provider=provider_name,
                is_active=True,
            ).first()
            if account:
                active_accounts.append(account)
        else:
            active_accounts = list(
                SocialMediaAccount.objects.filter(
                    organizer=request.organizer,
                    provider__in=["telegram", "mastodon", "postiz", "buffer"],
                    is_active=True,
                )
            )

        if not active_accounts:
            expected_prov = provider_name or "corresponding"
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        f"No active {expected_prov} account found to "
                        "publish this post."
                    ),
                },
                status=400,
            )

        errors = []
        published_providers = []

        for account in active_accounts:
            try:
                provider = get_provider(account)
                media = [db_post.media_url] if db_post.media_url else None
                provider.publish_post(text=db_post.post_text, media=media)
                published_providers.append(account.provider)
            except Exception as e:
                errors.append(f"{account.provider}: {str(e)}")

        if errors:
            db_post.status = SocialMediaPostStatus.FAILED
            err_details = "; ".join(errors)
            if published_providers:
                succ = ", ".join(published_providers)
                db_post.error_message = f"Published to ({succ}). Errors: {err_details}"
            else:
                db_post.error_message = err_details
            db_post.save()
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Publishing failed: {db_post.error_message}",
                    "status": db_post.status,
                },
                status=500,
            )

        is_scheduler = all(p in ["postiz", "buffer"] for p in published_providers)
        db_post.status = (
            SocialMediaPostStatus.EXPORTED
            if is_scheduler
            else SocialMediaPostStatus.PUBLISHED
        )
        db_post.error_message = ""
        db_post.save()

        return JsonResponse(
            {
                "success": True,
                "message": _("Post successfully published/synced!"),
                "status": db_post.status,
            }
        )

    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)

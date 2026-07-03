import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import FormView
from eventyay.control.views.event import DecoupleMixin

from .export import generate_csv_from_posts, sync_posts_to_db
from .forms import SocialMediaSettingsForm
from .models import SocialMediaPost


def _check_plugin_active(request):
    if "socialmedia" not in request.event.get_plugins():
        raise Http404("Social Media plugin is not enabled for this event.")


def _check_permission(request):
    if not request.user.has_event_permission(
        request.organizer,
        request.event,
        "can_change_event_settings",
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
        messages.success(self.request, _("Your changes have been saved."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            _("We could not save your changes. See below for details."),
        )
        return super().form_invalid(form)


def preview_posts(request, organizer, event):
    """AJAX GET — returns JSON list of generated posts synced with DB persistence."""
    _check_permission(request)
    _check_plugin_active(request)
    try:
        raw_posts = sync_posts_to_db(request.event, request)
        db_posts = {
            p.entity_id: p for p in SocialMediaPost.objects.filter(event=request.event)
        }
        posts = []
        for p in raw_posts:
            entity_id = str(p["id"])
            db_p = db_posts.get(entity_id)
            if db_p:
                p["db_id"] = db_p.pk
                p["status"] = db_p.status
                p["is_pinned"] = db_p.is_pinned
                p["post_text"] = db_p.post_text
                import pytz

                tz = pytz.timezone(getattr(request.event, "timezone", None) or "UTC")
                local_dt = db_p.scheduled_at.astimezone(tz)
                p["post_date"] = local_dt.strftime("%Y-%m-%d")
                p["post_time"] = local_dt.strftime("%H:%M")
            posts.append(p)
    except Exception as exc:  # pragma: no cover
        return JsonResponse({"error": str(exc)}, status=500)
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
            return JsonResponse({"error": "Post not found"}, status=404)

        if post_text is not None:
            db_post.post_text = post_text
        if status is not None:
            db_post.status = status
        if post_date and post_time:
            from datetime import datetime

            import pytz

            tz = pytz.timezone(getattr(request.event, "timezone", None) or "UTC")
            dt_str = f"{post_date} {post_time}"
            naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            db_post.scheduled_at = tz.localize(naive_dt)

        if is_pinned is not None:
            db_post.is_pinned = is_pinned
        else:
            db_post.is_pinned = True
        db_post.save()
        return JsonResponse(
            {"status": "ok", "db_id": db_post.pk, "is_pinned": db_post.is_pinned}
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@require_POST
def export_csv(request, organizer, event):
    """POST — receives final post list from frontend, returns CSV download."""
    _check_permission(request)
    _check_plugin_active(request)

    try:
        body = json.loads(request.body)
        posts = body.get("posts", [])
    except (json.JSONDecodeError, KeyError):
        return HttpResponse("Invalid request body.", status=400)

    csv_data = generate_csv_from_posts(posts)
    filename = f"{request.event.slug}_socialmedia_posts.csv"
    response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

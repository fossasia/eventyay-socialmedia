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

from .export import build_posts, generate_csv_from_posts
from .forms import SocialMediaSettingsForm


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
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        if form.has_changed():
            form.save()
            self._save_decoupled(form)
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
    """AJAX GET — returns JSON list of generated posts from live DB data."""
    _check_permission(request)
    _check_plugin_active(request)
    try:
        posts = build_posts(request.event, request)
    except Exception as exc:  # pragma: no cover
        return JsonResponse({"error": str(exc)}, status=500)
    return JsonResponse({"posts": posts})


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

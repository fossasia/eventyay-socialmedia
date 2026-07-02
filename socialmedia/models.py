from django.db import models
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Event


class SocialMediaPostStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    SCHEDULED = "scheduled", _("Scheduled")
    PUBLISHED = "published", _("Published")
    FAILED = "failed", _("Failed")
    EXPORTED = "exported", _("Exported")
    EXCLUDED = "excluded", _("Excluded")


class SocialMediaPost(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="social_media_posts",
    )
    post_type = models.CharField(
        max_length=30,
        help_text=_("Type of post: cfp, speaker, session, ticket, schedule, custom"),
    )
    entity_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Identifier of linked entity (e.g. submission PK, speaker PK)"),
    )
    scheduled_at = models.DateTimeField(
        help_text=_("Target date and time for publication"),
    )
    post_text = models.TextField(
        help_text=_("Social media copy"),
    )
    offset_days = models.IntegerField(
        default=0,
        help_text=_("Offset days or minutes used during generation"),
    )
    template_context = models.CharField(
        max_length=50,
        default="default",
        help_text=_("Template context key e.g. announcement, reminder"),
    )
    status = models.CharField(
        max_length=20,
        choices=SocialMediaPostStatus.choices,
        default=SocialMediaPostStatus.DRAFT,
    )
    is_pinned = models.BooleanField(
        default=False,
        help_text=_("True if manually locked or custom added by organizer"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_at"]
        verbose_name = _("Social Media Post")
        verbose_name_plural = _("Social Media Posts")

    def __str__(self):
        return f"[{self.post_type}] {self.event.slug} - {self.scheduled_at}"

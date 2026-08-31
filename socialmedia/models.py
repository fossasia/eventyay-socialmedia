from django.db import models
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Event, Organizer


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
    media_url = models.URLField(
        max_length=1024,
        blank=True,
        null=True,
        help_text=_("URL of the media/image attachment (e.g. speaker avatar)"),
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text=_("Error logs or failure reason returned by the provider API"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_at"]
        verbose_name = _("Social Media Post")
        verbose_name_plural = _("Social Media Posts")
        unique_together = [("event", "post_type", "entity_id", "offset_days")]

    def __str__(self):
        return f"[{self.post_type}] {self.event.slug} - {self.scheduled_at}"


class SocialMediaAccount(models.Model):
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name="social_media_accounts",
    )
    provider = models.CharField(
        max_length=20,
        choices=[
            ("mastodon", _("Mastodon")),
            ("telegram", _("Telegram")),
            ("twitter", _("Twitter / X")),
            ("linkedin", _("LinkedIn")),
        ],
    )
    platform_username = models.CharField(
        max_length=255,
        help_text=_("e.g. channel ID or username handle"),
    )
    encrypted_credentials = models.TextField(
        blank=True,
        default="",
        help_text=_("Fernet-encrypted JSON credentials blob"),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("True if this integration connection is active"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Social Media Account")
        verbose_name_plural = _("Social Media Accounts")
        unique_together = [("organizer", "provider", "platform_username")]

    def __str__(self):
        return f"{self.provider} - {self.platform_username} ({self.organizer.slug})"

    @property
    def credentials(self) -> dict:
        from .crypto import decrypt_credentials

        return decrypt_credentials(self.encrypted_credentials)

    @credentials.setter
    def credentials(self, data: dict):
        from .crypto import encrypt_credentials

        self.encrypted_credentials = encrypt_credentials(data)

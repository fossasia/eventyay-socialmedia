from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

from . import __version__

try:
    from eventyay.base.plugins import PluginConfig
except ImportError as e:
    raise ImproperlyConfigured(
        "Please use a later version of eventyay core package"
    ) from e


class SocialMediaPluginApp(PluginConfig):
    default = True
    name = "socialmedia"
    verbose_name = _("Social Media")

    class EventyayPluginMeta:
        name = _("Social Media")
        author = "FOSSASIA"
        description = _("Social media automation plugin for eventyay")
        visible = True
        version = __version__
        category = "FEATURE"

    def ready(self):
        from .operational_log import log_plugin_loaded

        log_plugin_loaded("socialmedia")
        from . import signals  # NOQA
        from . import tasks  # NOQA

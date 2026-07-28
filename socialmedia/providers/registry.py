from .base import BaseSocialProvider
from .buffer import BufferProvider
from .linkedin import LinkedInProvider
from .mastodon import MastodonProvider
from .postiz import PostizProvider
from .telegram import TelegramProvider
from .twitter import TwitterProvider

_registry: dict[str, type[BaseSocialProvider]] = {
    "telegram": TelegramProvider,
    "mastodon": MastodonProvider,
    "twitter": TwitterProvider,
    "linkedin": LinkedInProvider,
    "postiz": PostizProvider,
    "buffer": BufferProvider,
}


def get_provider_class(provider_name: str) -> type[BaseSocialProvider]:
    """Retrieve the provider adapter class for the given provider name.

    Args:
        provider_name (str): The name of the provider (e.g. 'telegram', 'mastodon').

    Returns:
        Type[BaseSocialProvider]: The provider adapter class.

    Raises:
        ValueError: If the provider is not supported or registered.
    """
    if provider_name not in _registry:
        raise ValueError(
            f"Unsupported or unregistered social media provider: {provider_name}"
        )
    return _registry[provider_name]


def get_provider(account) -> BaseSocialProvider:
    """Instantiate and return the provider adapter for the given SocialMediaAccount.

    Args:
        account (SocialMediaAccount): The account instance with provider credentials.

    Returns:
        BaseSocialProvider: An instance of the provider adapter.
    """
    provider_cls = get_provider_class(account.provider)
    return provider_cls(account)

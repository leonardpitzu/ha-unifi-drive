"""Translatable exception helpers for UniFi Drive user-facing actions."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN


def unifi_unas_error(
    message: str,
    translation_key: str,
    **placeholders: str,
) -> HomeAssistantError:
    """Return a translatable Home Assistant error with a fallback message."""
    try:
        return HomeAssistantError(
            message,
            translation_domain=DOMAIN,
            translation_key=translation_key,
            translation_placeholders=placeholders or None,
        )
    except TypeError:
        # Lightweight test stubs may not accept Home Assistant's keyword
        # arguments. Keep the same public attributes so helper tests still
        # verify the translation contract.
        err = HomeAssistantError(message)
        err.translation_domain = DOMAIN
        err.translation_key = translation_key
        err.translation_placeholders = placeholders or None
        return err


def unifi_unas_validation_error(
    message: str,
    translation_key: str,
    **placeholders: str,
) -> ServiceValidationError:
    """Return a translatable service validation error with a fallback message."""
    try:
        return ServiceValidationError(
            message,
            translation_domain=DOMAIN,
            translation_key=translation_key,
            translation_placeholders=placeholders or None,
        )
    except TypeError:
        err = ServiceValidationError(message)
        err.translation_domain = DOMAIN
        err.translation_key = translation_key
        err.translation_placeholders = placeholders or None
        return err

"""Store provider credentials in the local operating-system keychain."""

from __future__ import annotations

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


SERVICE_NAME = "dk.cbs.xhaile-legal-evaluation"


class CredentialStoreError(RuntimeError):
    """Raised when the operating-system credential store cannot be used."""


def get_api_key(account: str) -> str:
    try:
        return keyring.get_password(SERVICE_NAME, account) or ""
    except KeyringError as exc:
        raise CredentialStoreError("The API key could not be read from macOS Keychain.") from exc


def save_api_key(account: str, api_key: str) -> None:
    if not api_key:
        return
    try:
        keyring.set_password(SERVICE_NAME, account, api_key)
    except KeyringError as exc:
        raise CredentialStoreError("The API key could not be saved in macOS Keychain.") from exc


def delete_api_key(account: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, account)
    except PasswordDeleteError:
        return
    except KeyringError as exc:
        raise CredentialStoreError("The API key could not be removed from macOS Keychain.") from exc

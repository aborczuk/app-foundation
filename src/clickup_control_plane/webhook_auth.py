"""ClickUp webhook signature verification helpers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from collections.abc import Mapping


class SignatureVerificationError(ValueError):
    """Raised when a webhook signature is missing or invalid."""


def require_signature_header(headers: Mapping[str, str], *, header_name: str = "X-Signature") -> str:
    """Return the signature header value or raise for missing/blank input."""
    signature = headers.get(header_name, "")
    if not signature and header_name:
        # FastAPI header containers are case-insensitive, but generic Mapping inputs in
        # unit tests or adapters may not be. Fall back to explicit key normalization.
        lookup_name = header_name.strip().lower()
        if lookup_name:
            for key, value in headers.items():
                if key.strip().lower() == lookup_name:
                    signature = value
                    break
    if not signature or not signature.strip():
        raise SignatureVerificationError(f"Missing required signature header: {header_name}")
    return signature.strip()


def build_expected_signature(secret: str, body: bytes) -> str:
    """Return canonical hex HMAC-SHA256 signature for the payload."""
    normalized_secret = secret.strip()
    if not normalized_secret:
        raise SignatureVerificationError("Webhook secret cannot be blank.")
    digest = hmac.new(
        normalized_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return digest


def verify_clickup_signature(*, body: bytes, signature_header: str, webhook_secret: str) -> bool:
    """Return True when provided signature matches expected payload signature.

    Accepted formats:
    - `<hex>`
    - `sha256=<hex>`
    - base64-encoded digest bytes
    """
    expected_hex = build_expected_signature(webhook_secret, body)
    provided = signature_header.strip()
    normalized = provided.split("=", 1)[1] if provided.lower().startswith("sha256=") else provided
    normalized = normalized.strip()
    if not normalized:
        return False

    if hmac.compare_digest(normalized.lower(), expected_hex.lower()):
        return True

    try:
        decoded = base64.b64decode(normalized.encode("utf-8"), validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError):
        return False

    expected_bytes = bytes.fromhex(expected_hex)
    return hmac.compare_digest(decoded, expected_bytes)


def assert_valid_clickup_signature(
    *,
    body: bytes,
    headers: Mapping[str, str],
    webhook_secret: str,
    header_name: str = "X-Signature",
) -> None:
    """Raise SignatureVerificationError when the incoming signature is invalid."""
    signature = require_signature_header(headers, header_name=header_name)
    if not verify_clickup_signature(
        body=body,
        signature_header=signature,
        webhook_secret=webhook_secret,
    ):
        raise SignatureVerificationError("Invalid webhook signature.")


__all__ = [
    "SignatureVerificationError",
    "assert_valid_clickup_signature",
    "build_expected_signature",
    "require_signature_header",
    "verify_clickup_signature",
]

"""Unit tests for ClickUp webhook signature verification helpers."""

from __future__ import annotations

import base64

import pytest

from clickup_control_plane.webhook_auth import (
    SignatureVerificationError,
    assert_valid_clickup_signature,
    build_expected_signature,
    require_signature_header,
    verify_clickup_signature,
)


def test_require_signature_header_accepts_exact_case_and_case_insensitive_keys() -> None:
    """Test the expected behavior."""
    headers = {"X-Signature": "  hex-value  "}
    assert require_signature_header(headers) == "hex-value"

    mixed_case_headers = {"x-signature": "  other-value  "}
    assert require_signature_header(mixed_case_headers) == "other-value"


@pytest.mark.parametrize(
    ("headers", "expected_message"),
    [
        ({}, "Missing required signature header: X-Signature"),
        ({"X-Signature": "   "}, "Missing required signature header: X-Signature"),
    ],
)
def test_require_signature_header_raises_on_missing_or_blank(
    headers: dict[str, str],
    expected_message: str,
) -> None:
    """Test the expected behavior."""
    with pytest.raises(SignatureVerificationError, match=expected_message):
        require_signature_header(headers)


def test_verify_clickup_signature_accepts_hex_sha256_prefix_and_base64() -> None:
    """Test the expected behavior."""
    body = b'{"event":"taskUpdated","task_id":"task-123"}'
    secret = "webhook-secret"
    expected_hex = build_expected_signature(secret, body)
    expected_base64 = base64.b64encode(bytes.fromhex(expected_hex)).decode("ascii")

    assert verify_clickup_signature(
        body=body,
        signature_header=expected_hex,
        webhook_secret=secret,
    )
    assert verify_clickup_signature(
        body=body,
        signature_header=f"sha256={expected_hex}",
        webhook_secret=secret,
    )
    assert verify_clickup_signature(
        body=body,
        signature_header=expected_base64,
        webhook_secret=secret,
    )


def test_verify_clickup_signature_rejects_wrong_signature() -> None:
    """Test the expected behavior."""
    body = b'{"event":"taskUpdated","task_id":"task-123"}'
    secret = "webhook-secret"

    assert not verify_clickup_signature(
        body=body,
        signature_header="deadbeef",
        webhook_secret=secret,
    )


def test_assert_valid_clickup_signature_raises_on_invalid_signature() -> None:
    """Test the expected behavior."""
    body = b'{"event":"taskUpdated","task_id":"task-123"}'
    secret = "webhook-secret"
    headers = {"X-Signature": "deadbeef"}

    with pytest.raises(SignatureVerificationError, match="Invalid webhook signature."):
        assert_valid_clickup_signature(
            body=body,
            headers=headers,
            webhook_secret=secret,
        )

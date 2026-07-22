"""Authorization and payload contracts for Google Sheets delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import gspread
import pytest

from financial_tracker.exports.google_sheets import (
    GoogleSheetsDeliveryService,
    GoogleSheetsDestination,
)
from financial_tracker.exports.xlsx import ExportManifest, XlsxExportArtifact
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.persistence.models import QualityState
from financial_tracker.query.analysis import AnalysisRow


@dataclass
class _Worksheet:
    cleared: int = 0
    updated: tuple[str, list[list[str]], dict[str, object]] | None = None

    def clear(self) -> None:
        self.cleared += 1

    def update(self, range_name: str, values: list[list[str]], **kwargs: object) -> None:
        self.updated = (range_name, values, kwargs)


class _Spreadsheet:
    def __init__(self) -> None:
        self.id = "sheet-1"
        self.worksheet_value = _Worksheet()

    def worksheet(self, title: str) -> _Worksheet:
        assert title == "analysis"
        return self.worksheet_value

    def add_worksheet(self, title: str, rows: int, cols: int) -> _Worksheet:
        raise AssertionError("existing worksheet should be used")


class _Client:
    def __init__(self) -> None:
        self.spreadsheet = _Spreadsheet()
        self.opened_key: str | None = None

    def open_by_key(self, key: str) -> _Spreadsheet:
        self.opened_key = key
        return self.spreadsheet

    def create(self, title: str) -> _Spreadsheet:
        raise AssertionError("existing spreadsheet should be used")


class _NewSpreadsheet(_Spreadsheet):
    def worksheet(self, title: str) -> _Worksheet:
        raise gspread.WorksheetNotFound(title)

    def add_worksheet(self, title: str, rows: int, cols: int) -> _Worksheet:
        assert title == "new-analysis"
        assert rows == 1000
        assert cols == 14
        return self.worksheet_value


class _CreatingClient(_Client):
    def __init__(self) -> None:
        super().__init__()
        self.spreadsheet = _NewSpreadsheet()
        self.created_title: str | None = None

    def create(self, title: str) -> _NewSpreadsheet:
        self.created_title = title
        return self.spreadsheet


def _scope(issuer_id) -> AuthorizationScope:
    """Build a server-derived scope for one tenant-owned issuer."""
    return AuthorizationScope(
        user_id=uuid4(),
        tenant_id="tenant-a",
        subject_id="subject-a",
        portfolio_ids=frozenset({uuid4()}),
        issuer_ids=frozenset({issuer_id}),
    )


def _artifact(scope: AuthorizationScope, issuer_id) -> XlsxExportArtifact:
    """Build a minimal authorized artifact for delivery tests."""
    row = AnalysisRow(
        issuer_id=issuer_id,
        fiscal_period_id=uuid4(),
        metric_id="revenue_acceleration",
        definition_version="3",
        definition_hash="hash-v3",
        definition_state="active",
        value=None,
        quality_state=QualityState.VERIFIED,
        analysis_run_id=uuid4(),
        freshness="fresh",
        source_accessions=("acc-1",),
        source_fact_selectors=("Revenue",),
        calculated_at=datetime(2026, 1, 1),
        correlation_id="corr-1",
    )
    manifest = ExportManifest(
        requester_id=scope.user_id,
        schema_version="1",
        filters={},
        source_accessions=("acc-1",),
        content_hash="hash-content",
    )
    return XlsxExportArtifact(content=b"xlsx", rows=(row,), manifest=manifest)


def test_google_sheets_delivery_preserves_rows_and_scope() -> None:
    """Delivery writes the authorized artifact to the exact selected worksheet."""
    issuer_id = uuid4()
    scope = _scope(issuer_id)
    client = _Client()
    destination = GoogleSheetsDestination(
        owner_id=scope.user_id,
        credential_id="credential-a",
        spreadsheet_id="spreadsheet-a",
        worksheet_title="analysis",
    )

    artifact = _artifact(scope, issuer_id)
    receipt = GoogleSheetsDeliveryService(client, credential_id="credential-a").deliver(
        artifact,
        scope=scope,
        destination=destination,
        requested_by=scope.user_id,
    )

    assert client.opened_key == "spreadsheet-a"
    assert receipt.spreadsheet_id == "sheet-1"
    assert receipt.row_count == 1
    assert client.spreadsheet.worksheet_value.cleared == 1
    assert client.spreadsheet.worksheet_value.updated is not None
    assert client.spreadsheet.worksheet_value.updated[0] == "A1"
    assert client.spreadsheet.worksheet_value.updated[2] == {"value_input_option": "RAW"}
    assert client.spreadsheet.worksheet_value.updated[1] == [
        [
            "issuer_id",
            "fiscal_period_id",
            "metric_id",
            "definition_version",
            "definition_hash",
            "definition_state",
            "value",
            "quality_state",
            "analysis_run_id",
            "freshness",
            "source_accessions",
            "source_fact_selectors",
            "calculated_at",
            "correlation_id",
        ],
        [
            str(artifact.rows[0].issuer_id),
            str(artifact.rows[0].fiscal_period_id),
            artifact.rows[0].metric_id,
            artifact.rows[0].definition_version,
            artifact.rows[0].definition_hash,
            artifact.rows[0].definition_state,
            "" if artifact.rows[0].value is None else str(artifact.rows[0].value),
            str(artifact.rows[0].quality_state),
            str(artifact.rows[0].analysis_run_id),
            artifact.rows[0].freshness,
            ";".join(artifact.rows[0].source_accessions),
            ";".join(artifact.rows[0].source_fact_selectors),
            artifact.rows[0].calculated_at.isoformat(),
            artifact.rows[0].correlation_id or "",
        ],
    ]


def test_google_sheets_delivery_rejects_owner_mismatch() -> None:
    """Destination ownership is checked before any client operation."""
    issuer_id = uuid4()
    scope = _scope(issuer_id)
    client = _Client()
    destination = GoogleSheetsDestination(
        owner_id=uuid4(),
        credential_id="credential-b",
        spreadsheet_id="spreadsheet-a",
        worksheet_title="analysis",
    )

    with pytest.raises(AuthorizationError):
        GoogleSheetsDeliveryService(client, credential_id="credential-a").deliver(
            _artifact(scope, issuer_id),
            scope=scope,
            destination=destination,
            requested_by=scope.user_id,
        )

    assert client.opened_key is None


def test_google_sheets_delivery_rejects_credential_mismatch() -> None:
    """Configured credential identity is checked independently of ownership."""
    issuer_id = uuid4()
    scope = _scope(issuer_id)
    client = _Client()
    destination = GoogleSheetsDestination(
        owner_id=scope.user_id,
        credential_id="credential-b",
        spreadsheet_id="spreadsheet-a",
        worksheet_title="analysis",
    )

    with pytest.raises(AuthorizationError):
        GoogleSheetsDeliveryService(client, credential_id="credential-a").deliver(
            _artifact(scope, issuer_id),
            scope=scope,
            destination=destination,
            requested_by=scope.user_id,
        )

    assert client.opened_key is None


def test_google_sheets_delivery_creates_only_the_requested_new_destination() -> None:
    """New-sheet delivery uses the explicit title and worksheet selection."""
    issuer_id = uuid4()
    scope = _scope(issuer_id)
    client = _CreatingClient()
    destination = GoogleSheetsDestination(
        owner_id=scope.user_id,
        credential_id="credential-a",
        worksheet_title="new-analysis",
        new_spreadsheet_title="Quarterly metrics",
    )

    receipt = GoogleSheetsDeliveryService(client, credential_id="credential-a").deliver(
        _artifact(scope, issuer_id),
        scope=scope,
        destination=destination,
        requested_by=scope.user_id,
    )

    assert client.created_title == "Quarterly metrics"
    assert receipt.spreadsheet_id == "sheet-1"
    assert client.spreadsheet.worksheet_value.cleared == 1

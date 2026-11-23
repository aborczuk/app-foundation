"""Explicitly authorized Google Sheets delivery for analysis exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

import gspread

from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.query.analysis import AnalysisRow

if TYPE_CHECKING:
    from financial_tracker.exports.xlsx import XlsxExportArtifact


_HEADERS = (
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
)


@dataclass(frozen=True, slots=True)
class GoogleSheetsDestination:
    """Owner-bound spreadsheet destination selected by the authenticated user."""

    owner_id: UUID
    credential_id: str
    worksheet_title: str
    spreadsheet_id: str | None = None
    new_spreadsheet_title: str | None = None


@dataclass(frozen=True, slots=True)
class GoogleSheetsDeliveryReceipt:
    """Immutable result of one authorized Google Sheets delivery."""

    requester_id: UUID
    credential_id: str
    spreadsheet_id: str
    worksheet_title: str
    row_count: int
    content_hash: str


class WorksheetLike(Protocol):
    """Minimal worksheet behavior used by the delivery seam."""

    def clear(self) -> object:
        """Clear the selected worksheet before replacing its contents."""
        ...

    def update(self, range_name: str, values: list[list[str]], **kwargs: object) -> object:
        """Write the complete export matrix to the selected worksheet."""
        ...


class SpreadsheetLike(Protocol):
    """Minimal spreadsheet behavior used by the delivery seam."""

    id: str

    def worksheet(self, title: str) -> WorksheetLike:
        """Select an existing worksheet by its exact title."""
        ...

    def add_worksheet(self, title: str, rows: int, cols: int) -> WorksheetLike:
        """Create a worksheet with the explicitly selected title."""
        ...


class SheetsClientLike(Protocol):
    """Minimal authenticated gspread client behavior used by the adapter."""

    def open_by_key(self, key: str) -> SpreadsheetLike:
        """Open the explicitly selected spreadsheet."""
        ...

    def create(self, title: str) -> SpreadsheetLike:
        """Create a spreadsheet with the explicitly selected title."""
        ...


class GoogleSheetsDeliveryService:
    """Deliver an authorized analysis artifact through one configured client scope."""

    def __init__(self, client: object, *, credential_id: str) -> None:
        """Bind the adapter to one already-authenticated, server-owned gspread client."""
        self._client = cast(SheetsClientLike, client)
        self._credential_id = credential_id

    def deliver(
        self,
        artifact: "XlsxExportArtifact",
        *,
        scope: AuthorizationScope,
        destination: GoogleSheetsDestination,
        requested_by: UUID,
    ) -> GoogleSheetsDeliveryReceipt:
        """Replace one explicitly selected worksheet after checking all ownership seams."""
        if requested_by != scope.user_id:
            raise AuthorizationError("sheets requester does not match authenticated scope")
        if destination.owner_id != scope.user_id:
            raise AuthorizationError("sheets destination is outside the authenticated user scope")
        if destination.credential_id != self._credential_id:
            raise AuthorizationError("sheets credential is outside the configured delivery scope")
        if artifact.manifest.requester_id != scope.user_id:
            raise AuthorizationError("export artifact is outside the authenticated user scope")
        if not destination.worksheet_title.strip():
            raise ValueError("worksheet title must not be empty")
        for row in artifact.rows:
            if row.issuer_id not in scope.issuer_ids:
                raise AuthorizationError("sheets row is outside the authenticated issuer scope")

        spreadsheet = self._open_spreadsheet(destination)
        worksheet = self._worksheet(spreadsheet, destination.worksheet_title)
        values = [list(_HEADERS), *[_row_values(row) for row in artifact.rows]]
        worksheet.clear()
        worksheet.update("A1", values, value_input_option="RAW")
        return GoogleSheetsDeliveryReceipt(
            requester_id=requested_by,
            credential_id=destination.credential_id,
            spreadsheet_id=spreadsheet.id,
            worksheet_title=destination.worksheet_title,
            row_count=len(artifact.rows),
            content_hash=artifact.manifest.content_hash,
        )

    def _open_spreadsheet(self, destination: GoogleSheetsDestination) -> SpreadsheetLike:
        """Open only the requested spreadsheet or create the requested new one."""
        if destination.spreadsheet_id is not None:
            return self._client.open_by_key(destination.spreadsheet_id)
        title = destination.new_spreadsheet_title
        if title is None or not title.strip():
            raise ValueError("new spreadsheet title is required when spreadsheet_id is absent")
        return self._client.create(title)

    @staticmethod
    def _worksheet(spreadsheet: SpreadsheetLike, title: str) -> WorksheetLike:
        """Select an existing worksheet or create the explicitly named new worksheet."""
        try:
            return spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(title, rows=1000, cols=len(_HEADERS))


def _row_values(row: AnalysisRow) -> list[str]:
    """Convert one shared analysis row to exact string-preserving sheet values."""
    return [
        str(row.issuer_id),
        str(row.fiscal_period_id),
        row.metric_id,
        row.definition_version,
        row.definition_hash,
        row.definition_state,
        "" if row.value is None else str(row.value),
        str(row.quality_state),
        str(row.analysis_run_id),
        row.freshness,
        ";".join(row.source_accessions),
        ";".join(row.source_fact_selectors),
        row.calculated_at.isoformat(),
        row.correlation_id or "",
    ]

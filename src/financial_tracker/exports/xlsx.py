"""Deterministic XLSX export of the shared authorized analysis projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

import xlsxwriter

from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.query.analysis import AnalysisRow


@dataclass(frozen=True, slots=True)
class ExportManifest:
    """Immutable metadata describing one authorized export artifact."""

    requester_id: UUID
    schema_version: str
    filters: Mapping[str, str]
    source_accessions: tuple[str, ...]
    content_hash: str


@dataclass(frozen=True, slots=True)
class XlsxExportArtifact:
    """Generated workbook bytes, source rows, and its immutable manifest."""

    content: bytes
    rows: tuple[AnalysisRow, ...]
    manifest: ExportManifest


class XlsxExportService:
    """Authorize and serialize the shared analysis projection to XLSX."""

    def export(
        self,
        rows: tuple[AnalysisRow, ...] | list[AnalysisRow],
        *,
        scope: AuthorizationScope,
        filters: Mapping[str, str],
        requested_by: UUID,
        schema_version: str,
    ) -> XlsxExportArtifact:
        """Build deterministic workbook bytes after validating every row's scope."""
        if requested_by != scope.user_id:
            raise AuthorizationError("export requester does not match authenticated scope")
        normalized_filters = _normalize_filters(filters)
        issuer_filter = normalized_filters.get("issuer_id")
        _parse_issuer_filter(issuer_filter, scope)
        candidate_rows = tuple(rows)
        for row in candidate_rows:
            if row.issuer_id not in scope.issuer_ids:
                raise AuthorizationError("export row is outside the authenticated issuer scope")
        export_rows = tuple(
            sorted(
                _apply_filters(candidate_rows, normalized_filters),
                key=_row_sort_key,
            )
        )
        content = _render_workbook(export_rows)
        manifest = ExportManifest(
            requester_id=requested_by,
            schema_version=schema_version,
            filters=MappingProxyType(normalized_filters),
            source_accessions=tuple(
                accession
                for row in export_rows
                for accession in row.source_accessions
            ),
            content_hash=sha256(content).hexdigest(),
        )
        return XlsxExportArtifact(content=content, rows=export_rows, manifest=manifest)


def _normalize_filters(filters: Mapping[str, str]) -> dict[str, str]:
    """Normalize export filters into a stable string-keyed mapping."""
    return dict(sorted((str(key), str(value)) for key, value in filters.items()))


_FILTER_FIELDS = frozenset(
    {
        "issuer_id",
        "fiscal_period_id",
        "metric_id",
        "definition_version",
        "definition_hash",
        "definition_state",
        "quality_state",
        "analysis_run_id",
        "freshness",
        "correlation_id",
    }
)


def _apply_filters(
    rows: tuple[AnalysisRow, ...], filters: Mapping[str, str]
) -> tuple[AnalysisRow, ...]:
    """Apply the supported projection filters before serializing the workbook."""
    unsupported = set(filters) - _FILTER_FIELDS
    if unsupported:
        raise ValueError(f"unsupported export filters: {sorted(unsupported)}")
    return tuple(
        row
        for row in rows
        if all(_row_filter_value(row, key) == value for key, value in filters.items())
    )


def _row_filter_value(row: AnalysisRow, key: str) -> str:
    """Return one stable string representation for an export filter field."""
    value = getattr(row, key)
    if value is None:
        return ""
    return str(value)


def _row_sort_key(row: AnalysisRow) -> tuple[str, ...]:
    """Return a stable total-order key for deterministic workbook rows."""
    return (
        str(row.issuer_id),
        str(row.fiscal_period_id),
        row.metric_id,
        row.definition_version,
        str(row.analysis_run_id),
    )


def _parse_issuer_filter(value: str | None, scope: AuthorizationScope) -> UUID | None:
    """Parse and authorize an optional issuer filter before workbook creation."""
    if value is None:
        return None
    try:
        issuer_id = UUID(value)
    except ValueError as exc:
        raise AuthorizationError("issuer filter must be a valid issuer identifier") from exc
    if issuer_id not in scope.issuer_ids:
        raise AuthorizationError("issuer filter is outside the authenticated issuer scope")
    return issuer_id


def _render_workbook(rows: tuple[AnalysisRow, ...]) -> bytes:
    """Render the shared rows with fixed metadata and column order."""
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    workbook.set_properties({"created": datetime(2000, 1, 1)})
    worksheet = workbook.add_worksheet("analysis")
    headers = (
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
    header_format = workbook.add_format({"bold": True})
    for column, header in enumerate(headers):
        worksheet.write_string(0, column, header, header_format)
    for row_number, row in enumerate(rows, start=1):
        values = (
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
        )
        for column, value in enumerate(values):
            worksheet.write_string(row_number, column, value)
    worksheet.freeze_panes(1, 0)
    workbook.close()
    return output.getvalue()

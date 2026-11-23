"""Red parity and authorization contracts for API and XLSX projections."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html import unescape
from io import BytesIO
from re import DOTALL, findall, search
from uuid import uuid4
from zipfile import ZipFile

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.persistence.models import Provenance, QualityState
from financial_tracker.query.analysis import read_analysis


def _serialized_xlsx_rows(content: bytes) -> list[list[str]]:
    """Read the rendered analysis worksheet values from generated XLSX bytes."""
    with ZipFile(BytesIO(content)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_xml = archive.read("xl/sharedStrings.xml").decode("utf-8")
            shared_strings = [
                unescape(
                    "".join(findall(r"<t\b[^>]*>(.*?)</t>", item, DOTALL))
                )
                for item in findall(r"<si\b[^>]*>(.*?)</si>", shared_xml, DOTALL)
            ]
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        rows: list[list[str]] = []
        for row_xml in findall(r"<row\b[^>]*>(.*?)</row>", sheet_xml, DOTALL):
            values: list[str] = []
            for attributes, cell_xml in findall(
                r"<c\b([^>]*)>(.*?)</c>", row_xml, DOTALL
            ):
                inline = search(r"<is\b[^>]*>(.*?)</is>", cell_xml, DOTALL)
                value = search(r"<v\b[^>]*>(.*?)</v>", cell_xml, DOTALL)
                if inline is not None:
                    text = "".join(
                        findall(r"<t\b[^>]*>(.*?)</t>", inline.group(1), DOTALL)
                    )
                    values.append(unescape(text))
                elif value is None:
                    values.append("")
                elif 't="s"' in attributes:
                    values.append(shared_strings[int(value.group(1) or "0")])
                else:
                    values.append(unescape(value.group(1)))
            rows.append(values)
        return rows


def _scope(issuer_id) -> AuthorizationScope:
    """Build a server-derived scope for one tenant-owned issuer."""
    return AuthorizationScope(
        user_id=uuid4(),
        tenant_id="tenant-a",
        subject_id="subject-a",
        portfolio_ids=frozenset({uuid4()}),
        issuer_ids=frozenset({issuer_id}),
    )


def _observation(
    issuer_id,
    *,
    quality_state: QualityState,
    freshness: str,
    metric_id: str = "revenue_acceleration",
) -> MetricObservation:
    """Build one deterministic observation containing visible provenance."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    filing_id = uuid4()
    return MetricObservation(
        id=uuid4(),
        tenant_id="tenant-a",
        issuer_id=issuer_id,
        fiscal_period_id=uuid4(),
        metric_id=metric_id,
        definition_version="3",
        definition_hash="hash-v3",
        definition_state="active",
        calculation_version="calc-v1",
        source_snapshot_hash="snapshot-1",
        analysis_run_id=uuid4(),
        value=Decimal("12.50"),
        quality_state=quality_state,
        freshness=freshness,
        provenance=(
            Provenance(
                id=uuid4(),
                filing_id=filing_id,
                accession="0000320193-25-000001",
                source_url="https://www.sec.gov/Archives/edgar/data/example",
                selector="Revenue",
                captured_at=now,
            ),
        ),
        calculated_at=now,
    )


def test_api_projection_and_xlsx_export_preserve_the_same_rows() -> None:
    """XLSX consumes the authorized API rows without losing state or provenance."""
    from financial_tracker.exports.xlsx import XlsxExportService

    issuer_id = uuid4()
    scope = _scope(issuer_id)
    observations = [
        _observation(issuer_id, quality_state=QualityState.VERIFIED, freshness="fresh"),
        _observation(
            issuer_id,
            quality_state=QualityState.STALE,
            freshness="recalculation-pending",
        ),
    ]
    rows = read_analysis(scope, observations, issuer_id=issuer_id, correlation_id="corr-1")
    exporter = XlsxExportService()

    artifact = exporter.export(
        rows,
        scope=scope,
        filters={"issuer_id": str(issuer_id), "metric_id": "revenue_acceleration"},
        requested_by=scope.user_id,
        schema_version="1",
    )

    assert {row.analysis_run_id for row in artifact.rows} == {
        row.analysis_run_id for row in rows
    }
    assert artifact.manifest.schema_version == "1"
    assert artifact.manifest.filters == {
        "issuer_id": str(issuer_id),
        "metric_id": "revenue_acceleration",
    }
    assert artifact.manifest.source_accessions == (
        "0000320193-25-000001",
        "0000320193-25-000001",
    )
    assert artifact.manifest.content_hash == sha256(artifact.content).hexdigest()
    assert artifact.content
    assert _serialized_xlsx_rows(artifact.content) == [
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
        *[
            [
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
            for row in artifact.rows
        ],
    ]

    repeated = exporter.export(
        rows,
        scope=scope,
        filters={"issuer_id": str(issuer_id), "metric_id": "revenue_acceleration"},
        requested_by=scope.user_id,
        schema_version="1",
    )
    assert repeated.content == artifact.content
    assert repeated.manifest == artifact.manifest

    reordered = exporter.export(
        tuple(reversed(rows)),
        scope=scope,
        filters={"issuer_id": str(issuer_id), "metric_id": "revenue_acceleration"},
        requested_by=scope.user_id,
        schema_version="1",
    )
    assert reordered.content == artifact.content


def test_xlsx_export_applies_projection_filters_before_rendering() -> None:
    """Manifest filters select only matching authorized projection rows."""
    from financial_tracker.exports.xlsx import XlsxExportService

    issuer_id = uuid4()
    scope = _scope(issuer_id)
    rows = read_analysis(
        scope,
        [
            _observation(
                issuer_id,
                quality_state=QualityState.VERIFIED,
                freshness="fresh",
                metric_id="revenue_acceleration",
            ),
            _observation(
                issuer_id,
                quality_state=QualityState.VERIFIED,
                freshness="fresh",
                metric_id="margin_expansion",
            ),
        ],
        issuer_id=issuer_id,
    )

    artifact = XlsxExportService().export(
        rows,
        scope=scope,
        filters={"metric_id": "revenue_acceleration"},
        requested_by=scope.user_id,
        schema_version="1",
    )

    assert len(artifact.rows) == 1
    assert artifact.rows[0].metric_id == "revenue_acceleration"


def test_api_projection_denies_an_issuer_outside_authenticated_scope() -> None:
    """Unauthorized company access fails without returning financial rows."""
    issuer_id = uuid4()
    foreign_issuer_id = uuid4()
    scope = _scope(issuer_id)

    with pytest.raises(AuthorizationError):
        read_analysis(
            scope,
            [_observation(foreign_issuer_id, quality_state=QualityState.VERIFIED, freshness="fresh")],
            issuer_id=foreign_issuer_id,
        )


def test_xlsx_export_denies_rows_outside_authenticated_scope() -> None:
    """Export authorization cannot be bypassed with foreign rows or filters."""
    from financial_tracker.exports.xlsx import XlsxExportService

    issuer_id = uuid4()
    owner_scope = _scope(issuer_id)
    foreign_scope = _scope(uuid4())
    rows = read_analysis(
        owner_scope,
        [_observation(issuer_id, quality_state=QualityState.VERIFIED, freshness="fresh")],
        issuer_id=issuer_id,
    )

    with pytest.raises(AuthorizationError):
        XlsxExportService().export(
            rows,
            scope=foreign_scope,
            filters={"issuer_id": str(issuer_id)},
            requested_by=foreign_scope.user_id,
            schema_version="1",
        )

"""Immutable versioned metric-definition registry and history selection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity import AuthorizationError, AuthorizationScope, require_issuer_access

_VALID_STATES = frozenset({"draft", "active", "retired", "invalid"})


@dataclass(frozen=True, slots=True)
class MetricDefinitionVersion:
    """Immutable metric content identity with a lifecycle state projection."""

    metric_id: str
    tenant_id: str
    version: int
    expression: str
    content_hash: str
    output_unit: str
    state: str
    created_by: UUID
    created_at: datetime

    def __post_init__(self) -> None:
        """Reject definition records that cannot participate in versioned history."""
        if not self.metric_id or not self.tenant_id or not self.expression or not self.content_hash:
            raise ValueError("metric definition identity and content are required")
        if self.version < 1:
            raise ValueError("metric definition version must be positive")
        if not self.output_unit or self.state not in _VALID_STATES:
            raise ValueError("metric definition unit or state is invalid")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("metric definition timestamp must be timezone-aware")


class MetricRegistry:
    """Store definition versions without allowing content identity to be overwritten."""

    def __init__(self) -> None:
        """Create an empty tenant-scoped definition registry."""
        self._versions: dict[tuple[str, str, int], MetricDefinitionVersion] = {}

    def add_version(self, definition: MetricDefinitionVersion, *, scope: AuthorizationScope) -> None:
        """Authorize and persist a draft version without allowing content mutation."""
        self._authorize(definition, scope, require_owner=True)
        if definition.state != "draft":
            raise ValueError("new metric definition versions must start in draft state")
        key = (definition.tenant_id, definition.metric_id, definition.version)
        existing = self._versions.get(key)
        if existing is not None:
            if existing != definition:
                raise ValueError("metric definition version is immutable")
            return
        self._versions[key] = definition

    def get_version(
        self,
        metric_id: str,
        *,
        version: int,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion:
        """Return one exact tenant-scoped definition version or raise when absent."""
        try:
            definition = self._versions[(scope.tenant_id, metric_id, version)]
        except KeyError as exc:
            raise KeyError(f"metric definition version not found: {metric_id}:{version}") from exc
        self._authorize(definition, scope)
        return definition

    def versions(self, metric_id: str, *, scope: AuthorizationScope) -> tuple[MetricDefinitionVersion, ...]:
        """Return tenant-scoped versions for a metric in ascending order."""
        return tuple(
            sorted(
                (
                    item
                    for item in self._versions.values()
                    if item.tenant_id == scope.tenant_id and item.metric_id == metric_id
                ),
                key=lambda item: item.version,
            )
        )

    def active_version(self, metric_id: str, *, scope: AuthorizationScope) -> MetricDefinitionVersion | None:
        """Return the newest authorized active version without altering history."""
        active = [item for item in self.versions(metric_id, scope=scope) if item.state == "active"]
        return active[-1] if active else None

    def activate(
        self,
        metric_id: str,
        *,
        version: int,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion:
        """Authorize and activate a draft definition by replacing only its state projection."""
        definition = self._definition_for_write(metric_id, version, scope)
        self._authorize(definition, scope, require_owner=True)
        if definition.state == "active":
            return definition
        if definition.state != "draft":
            raise ValueError("only draft metric definitions can be activated")
        activated = replace(definition, state="active")
        self._versions[(scope.tenant_id, metric_id, version)] = activated
        return activated

    def retire(self, metric_id: str, *, scope: AuthorizationScope) -> None:
        """Authorize and retire every active version while retaining its history."""
        definitions = self.versions(metric_id, scope=scope)
        if not definitions:
            foreign = next((item for item in self._versions.values() if item.metric_id == metric_id), None)
            if foreign is not None:
                self._authorize(foreign, scope, require_owner=True)
            raise KeyError(f"metric definition not found: {metric_id}")
        for definition in definitions:
            self._authorize(definition, scope, require_owner=True)
        for definition in definitions:
            if definition.state in {"active", "draft"}:
                key = (definition.tenant_id, metric_id, definition.version)
                self._versions[key] = replace(definition, state="retired")

    def _definition_for_write(self, metric_id: str, version: int, scope: AuthorizationScope) -> MetricDefinitionVersion:
        """Resolve a version while preserving authorization errors for foreign tenants."""
        definition = self._versions.get((scope.tenant_id, metric_id, version))
        if definition is not None:
            return definition
        foreign = next(
            (item for item in self._versions.values() if item.metric_id == metric_id and item.version == version),
            None,
        )
        if foreign is not None:
            self._authorize(foreign, scope, require_owner=True)
        raise KeyError(f"metric definition version not found: {metric_id}:{version}")

    @staticmethod
    def _authorize(
        definition: MetricDefinitionVersion,
        scope: AuthorizationScope,
        *,
        require_owner: bool = False,
    ) -> None:
        """Enforce tenant isolation and optional definition ownership."""
        if definition.tenant_id != scope.tenant_id:
            raise AuthorizationError("metric definition is outside the authenticated tenant scope")
        if require_owner and definition.created_by != scope.user_id:
            raise AuthorizationError("metric definition is outside the authenticated user's scope")


class PostgresMetricRegistry:
    """Persist metric definition versions in the authoritative PostgreSQL store."""

    def __init__(self, connection: Any) -> None:
        """Bind the registry to an existing PostgreSQL connection."""
        self._connection = connection

    def add_version(self, definition: MetricDefinitionVersion, *, scope: AuthorizationScope) -> None:
        """Authorize and insert one draft version without overwriting its content."""
        MetricRegistry._authorize(definition, scope, require_owner=True)
        if definition.state != "draft":
            raise ValueError("new metric definition versions must start in draft state")
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO financial_tracker.metric_definition_versions
                        (tenant_id, metric_id, version, expression, content_hash, output_unit,
                         state, created_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, metric_id, version) DO NOTHING
                    """,
                    (
                        definition.tenant_id,
                        definition.metric_id,
                        definition.version,
                        definition.expression,
                        definition.content_hash,
                        definition.output_unit,
                        definition.state,
                        definition.created_by,
                        definition.created_at,
                    ),
                )
                cursor.execute(
                    """
                    SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                           state, created_by, created_at
                    FROM financial_tracker.metric_definition_versions
                    WHERE tenant_id = %s AND metric_id = %s AND version = %s
                    """,
                    (definition.tenant_id, definition.metric_id, definition.version),
                )
                persisted = self._from_row(cursor.fetchone())
            if persisted != definition:
                raise ValueError("metric definition version is immutable")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def get_version(
        self,
        metric_id: str,
        *,
        version: int,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion:
        """Return one exact tenant-scoped PostgreSQL definition version."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                       state, created_by, created_at
                FROM financial_tracker.metric_definition_versions
                WHERE tenant_id = %s AND metric_id = %s AND version = %s
                """,
                (scope.tenant_id, metric_id, version),
            )
            definition = self._from_row(cursor.fetchone())
        MetricRegistry._authorize(definition, scope)
        return definition

    def versions(self, metric_id: str, *, scope: AuthorizationScope) -> tuple[MetricDefinitionVersion, ...]:
        """Return tenant-scoped PostgreSQL versions in ascending order."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                       state, created_by, created_at
                FROM financial_tracker.metric_definition_versions
                WHERE tenant_id = %s AND metric_id = %s
                ORDER BY version ASC
                """,
                (scope.tenant_id, metric_id),
            )
            return tuple(self._from_row(row) for row in cursor.fetchall())

    def active_version(self, metric_id: str, *, scope: AuthorizationScope) -> MetricDefinitionVersion | None:
        """Return the newest active definition from PostgreSQL for one tenant."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                       state, created_by, created_at
                FROM financial_tracker.metric_definition_versions
                WHERE tenant_id = %s AND metric_id = %s AND state = 'active'
                ORDER BY version DESC
                LIMIT 1
                """,
                (scope.tenant_id, metric_id),
            )
            row = cursor.fetchone()
        return self._from_row(row) if row is not None else None

    def activate(
        self,
        metric_id: str,
        *,
        version: int,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion:
        """Authorize and atomically activate one draft PostgreSQL version."""
        try:
            with self._connection.cursor() as cursor:
                definition = self._fetch_for_write(cursor, metric_id, version, scope)
                MetricRegistry._authorize(definition, scope, require_owner=True)
                if definition.state == "active":
                    self._connection.commit()
                    return definition
                if definition.state != "draft":
                    raise ValueError("only draft metric definitions can be activated")
                cursor.execute(
                    """
                    UPDATE financial_tracker.metric_definition_versions
                    SET state = 'active'
                    WHERE tenant_id = %s AND metric_id = %s AND version = %s
                    """,
                    (scope.tenant_id, metric_id, version),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return replace(definition, state="active")

    def retire(self, metric_id: str, *, scope: AuthorizationScope) -> None:
        """Authorize and atomically retire all draft and active versions for a metric."""
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                           state, created_by, created_at
                    FROM financial_tracker.metric_definition_versions
                    WHERE tenant_id = %s AND metric_id = %s
                    FOR UPDATE
                    """,
                    (scope.tenant_id, metric_id),
                )
                definitions = tuple(self._from_row(row) for row in cursor.fetchall())
                if not definitions:
                    cursor.execute(
                        """
                        SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                               state, created_by, created_at
                        FROM financial_tracker.metric_definition_versions
                        WHERE metric_id = %s
                        LIMIT 1
                        """,
                        (metric_id,),
                    )
                    foreign = cursor.fetchone()
                    if foreign is not None:
                        MetricRegistry._authorize(self._from_row(foreign), scope, require_owner=True)
                    raise KeyError(f"metric definition not found: {metric_id}")
                for definition in definitions:
                    MetricRegistry._authorize(definition, scope, require_owner=True)
                cursor.execute(
                    """
                    UPDATE financial_tracker.metric_definition_versions
                    SET state = 'retired'
                    WHERE tenant_id = %s AND metric_id = %s AND state IN ('draft', 'active')
                    """,
                    (scope.tenant_id, metric_id),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    @staticmethod
    def _fetch_for_write(cursor: Any, metric_id: str, version: int, scope: AuthorizationScope) -> MetricDefinitionVersion:
        """Fetch a locked version while preserving foreign-tenant authorization errors."""
        cursor.execute(
            """
            SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                   state, created_by, created_at
            FROM financial_tracker.metric_definition_versions
            WHERE tenant_id = %s AND metric_id = %s AND version = %s
            FOR UPDATE
            """,
            (scope.tenant_id, metric_id, version),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                """
                SELECT tenant_id, metric_id, version, expression, content_hash, output_unit,
                       state, created_by, created_at
                FROM financial_tracker.metric_definition_versions
                WHERE metric_id = %s AND version = %s
                LIMIT 1
                FOR UPDATE
                """,
                (metric_id, version),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(f"metric definition version not found: {metric_id}:{version}")
            definition = PostgresMetricRegistry._from_row(row)
            MetricRegistry._authorize(definition, scope, require_owner=True)
            return definition
        return PostgresMetricRegistry._from_row(row)

    @staticmethod
    def _from_row(row: tuple[Any, ...] | None) -> MetricDefinitionVersion:
        """Map one PostgreSQL row to the immutable domain record."""
        if row is None:
            raise KeyError("metric definition version not found")
        return MetricDefinitionVersion(
            tenant_id=row[0],
            metric_id=row[1],
            version=row[2],
            expression=row[3],
            content_hash=row[4],
            output_unit=row[5],
            state=row[6],
            created_by=row[7],
            created_at=row[8],
        )


def select_observation(
    observations: Iterable[MetricObservation],
    *,
    metric_id: str,
    definition_version: str,
    scope: AuthorizationScope,
    issuer_id: UUID,
    fiscal_period_id: UUID,
    analysis_run_id: UUID,
) -> MetricObservation | None:
    """Select one tenant, issuer, period, run, and definition-version observation."""
    require_issuer_access(scope, issuer_id)
    return next(
        (
            observation
            for observation in observations
            if (
                observation.tenant_id == scope.tenant_id
                and observation.metric_id == metric_id
                and observation.definition_version == definition_version
                and observation.issuer_id == issuer_id
                and observation.fiscal_period_id == fiscal_period_id
                and observation.analysis_run_id == analysis_run_id
            )
        ),
        None,
    )

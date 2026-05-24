"""Shared helpers for DataForge CLI commands."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import resources
from pathlib import Path
from typing import cast

import typer
import yaml

from dataforge.table import Table
from dataforge.table import read_csv as read_table_csv
from dataforge.verifier.schema import (
    AggregateDependency,
    AggregateLiteral,
    DomainBound,
    FunctionalDependency,
    Schema,
)

_PACKAGED_DEMO_FIXTURES = {
    "fixtures/hospital_10rows.csv": "fixtures/hospital_10rows.csv",
    "fixtures/hospital_schema.yaml": "fixtures/hospital_schema.yaml",
}


def resolve_cli_path(path: Path) -> Path:
    """Resolve a user path, including DataForge's packaged demo fixture aliases."""
    if path.exists():
        return path

    normalized = path.as_posix().replace("\\", "/").lstrip("./")
    packaged_name = _PACKAGED_DEMO_FIXTURES.get(normalized)
    if packaged_name is None:
        return path

    fixture = resources.files("dataforge").joinpath(packaged_name)
    if not fixture.is_file():
        return path
    return Path(str(fixture))


def schema_from_mapping(raw_mapping: object) -> Schema:
    """Build a Schema from a raw YAML mapping-like payload.

    Args:
        raw_mapping: Untrusted YAML-decoded value.

    Returns:
        Parsed Schema object.

    Raises:
        typer.BadParameter: If the payload is not a mapping.
    """
    if raw_mapping is None:
        mapping: dict[str, object] = {}
    elif isinstance(raw_mapping, dict):
        mapping = raw_mapping
    else:
        raise typer.BadParameter("Schema payload must be a YAML mapping.")

    columns: dict[str, str] = {}
    raw_columns = mapping.get("columns", {})
    if isinstance(raw_columns, dict):
        columns = {str(key): str(value) for key, value in raw_columns.items()}

    fds: list[FunctionalDependency] = []
    raw_fds = mapping.get("functional_dependencies", [])
    if isinstance(raw_fds, list):
        for raw_fd in raw_fds:
            if not isinstance(raw_fd, dict):
                continue
            raw_determinant = raw_fd.get("determinant", [])
            determinant_values = (
                tuple(str(value) for value in raw_determinant)
                if isinstance(raw_determinant, Iterable)
                and not isinstance(raw_determinant, (str, bytes))
                else ()
            )
            fds.append(
                FunctionalDependency(
                    determinant=determinant_values,
                    dependent=str(raw_fd.get("dependent", "")),
                )
            )

    raw_pii_columns = mapping.get("pii_columns", [])
    pii_columns = (
        frozenset(str(value) for value in raw_pii_columns)
        if isinstance(raw_pii_columns, Iterable) and not isinstance(raw_pii_columns, (str, bytes))
        else frozenset()
    )

    bounds: list[DomainBound] = []
    raw_bounds = mapping.get("domain_bounds", {})
    if isinstance(raw_bounds, dict):
        for column, bound_payload in raw_bounds.items():
            if not isinstance(bound_payload, dict):
                continue
            bounds.append(
                DomainBound(
                    column=str(column),
                    min_value=(
                        float(bound_payload["min"])
                        if bound_payload.get("min") is not None
                        else None
                    ),
                    max_value=(
                        float(bound_payload["max"])
                        if bound_payload.get("max") is not None
                        else None
                    ),
                    inclusive_min=bool(bound_payload.get("inclusive_min", True)),
                    inclusive_max=bool(bound_payload.get("inclusive_max", True)),
                )
            )

    aggregate_dependencies: list[AggregateDependency] = []
    raw_aggregates = mapping.get("aggregate_dependencies", [])
    if isinstance(raw_aggregates, list):
        for raw_dependency in raw_aggregates:
            if not isinstance(raw_dependency, dict):
                continue
            raw_aggregate = str(raw_dependency.get("aggregate", "")).lower()
            if raw_aggregate not in {"sum", "avg"}:
                continue
            raw_group_by = raw_dependency.get("group_by", [])
            group_by = (
                tuple(str(value) for value in raw_group_by)
                if isinstance(raw_group_by, Iterable) and not isinstance(raw_group_by, (str, bytes))
                else ()
            )
            aggregate_dependencies.append(
                AggregateDependency(
                    source_column=str(raw_dependency.get("source_column", "")),
                    aggregate=cast(AggregateLiteral, raw_aggregate),
                    target_column=str(raw_dependency.get("target_column", "")),
                    group_by=group_by,
                )
            )

    return Schema(
        columns=columns,
        functional_dependencies=tuple(fds),
        pii_columns=pii_columns,
        domain_bounds=tuple(bounds),
        aggregate_dependencies=tuple(aggregate_dependencies),
    )


def load_schema(schema_path: Path) -> Schema:
    """Load a Schema from a YAML file.

    Args:
        schema_path: Path to the YAML schema file.

    Returns:
        Parsed Schema object.

    Raises:
        typer.BadParameter: If the schema file is malformed or unreadable.
    """
    try:
        raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise typer.BadParameter(f"Could not read schema file '{schema_path}': {exc}") from exc

    if raw is not None and not isinstance(raw, dict):
        raise typer.BadParameter(f"Schema file '{schema_path}' must be a YAML mapping.")
    return schema_from_mapping(raw)


def read_csv(path: Path) -> Table:
    """Read a CSV using conservative string-preserving defaults.

    Args:
        path: CSV path.

    Returns:
        A string-preserving DataForge table.
    """
    return read_table_csv(path)

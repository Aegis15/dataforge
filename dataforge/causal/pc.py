"""PC-based causal DAG discovery with functional-dependency priors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency  # type: ignore[import-untyped]

from dataforge.causal.dag import CausalDAG
from dataforge.verifier.schema import Schema

__all__ = ["CausalDiscoveryResult", "discover_causal_dag"]


@dataclass(frozen=True)
class CausalDiscoveryResult:
    """Result of causal discovery.

    Args:
        dag: Directed acyclic graph over columns.
        confidence_report: Column-pair confidence or diagnostic metadata.
        warnings: Non-fatal discovery warnings.
    """

    dag: CausalDAG
    confidence_report: dict[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def discover_causal_dag(
    df: pd.DataFrame,
    schema: Schema | None = None,
    *,
    alpha: float = 0.05,
) -> CausalDiscoveryResult:
    """Infer a deterministic causal DAG from tabular data and FD priors.

    Args:
        df: Input DataFrame.
        schema: Optional declared schema with functional dependencies.
        alpha: Significance threshold for independence checks.

    Returns:
        CausalDiscoveryResult. A DAG is returned even if PC orientation is
        underdetermined; low-confidence edges are tagged as such.
    """
    columns = [str(column) for column in df.columns]
    dag = CausalDAG(columns)
    report: dict[str, float] = {}
    warnings: list[str] = []

    if schema is not None:
        for fd in schema.functional_dependencies:
            for determinant in fd.determinant:
                _try_add_edge(
                    dag,
                    determinant,
                    fd.dependent,
                    confidence=0.95,
                    provenance="functional_dependency_prior",
                    warnings=warnings,
                )
                report[f"{determinant}->{fd.dependent}"] = 0.95

    cleaned = _prepare_for_pc(df)
    pc_edges, pc_warning = _run_causal_learn_pc(cleaned.to_numpy(), columns, alpha)
    if pc_warning:
        warnings.append(pc_warning)
    for source, target in pc_edges:
        _try_add_edge(
            dag,
            source,
            target,
            confidence=0.55,
            provenance="causal_learn_pc",
            warnings=warnings,
        )
        report.setdefault(f"{source}->{target}", 0.55)

    for source, target, confidence in _pairwise_dependency_edges(df, alpha):
        _try_add_edge(
            dag,
            source,
            target,
            confidence=confidence,
            provenance="pairwise_ci_fallback",
            warnings=warnings,
        )
        report.setdefault(f"{source}->{target}", confidence)

    return CausalDiscoveryResult(dag=dag, confidence_report=report, warnings=tuple(warnings))


def _prepare_for_pc(df: pd.DataFrame) -> pd.DataFrame:
    """Return numeric data with no NaN values for causal-learn PC."""
    prepared = pd.DataFrame(index=df.index)
    for column in df.columns:
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().sum() >= max(2, int(0.5 * len(df))):
            fill = float(numeric.median()) if numeric.notna().any() else 0.0
            prepared[str(column)] = numeric.fillna(fill)
        else:
            codes, _ = pd.factorize(df[column].astype("string").fillna("<missing>"), sort=True)
            prepared[str(column)] = codes.astype(float)
    return prepared.fillna(0.0)


def _run_causal_learn_pc(
    data: np.ndarray[Any, Any], columns: list[str], alpha: float
) -> tuple[list[tuple[str, str]], str | None]:
    """Run causal-learn PC and return deterministic directed edges."""
    try:
        from causallearn.search.ConstraintBased.PC import pc  # type: ignore[import-untyped]

        result = pc(data, alpha=alpha, indep_test="fisherz", stable=True, show_progress=False)
    except Exception as exc:
        return [], f"causal-learn PC unavailable or failed: {exc}"

    matrix = getattr(getattr(result, "G", None), "graph", None)
    if matrix is None:
        return [], "causal-learn PC returned no adjacency matrix"

    edges: list[tuple[str, str]] = []
    arr = np.asarray(matrix)
    for i, source in enumerate(columns):
        for j, target in enumerate(columns):
            if i >= j or i >= arr.shape[0] or j >= arr.shape[1]:
                continue
            if arr[i, j] != 0 or arr[j, i] != 0:
                edges.append((source, target))
    return edges, None


def _pairwise_dependency_edges(df: pd.DataFrame, alpha: float) -> list[tuple[str, str, float]]:
    """Return deterministic low-confidence edges for dependent column pairs."""
    columns = [str(column) for column in df.columns]
    edges: list[tuple[str, str, float]] = []
    for i, source in enumerate(columns):
        for target in columns[i + 1 :]:
            p_value = _pairwise_p_value(df[source], df[target])
            if p_value < alpha:
                confidence = max(0.25, min(0.75, 1.0 - p_value))
                edges.append((source, target, round(confidence, 4)))
    return edges


def _pairwise_p_value(left: pd.Series[Any], right: pd.Series[Any]) -> float:
    """Return a p-value using categorical, continuous, or mixed tests."""
    left_numeric = pd.to_numeric(left, errors="coerce")
    right_numeric = pd.to_numeric(right, errors="coerce")
    left_cont = left_numeric.notna().sum() >= max(5, int(0.8 * len(left)))
    right_cont = right_numeric.notna().sum() >= max(5, int(0.8 * len(right)))

    if left_cont and right_cont:
        return _hsic_p_value(
            left_numeric.fillna(left_numeric.median()), right_numeric.fillna(right_numeric.median())
        )
    if not left_cont and not right_cont:
        return _chi_squared_p_value(left, right)
    return _mutual_information_p_value(left, right)


def _chi_squared_p_value(left: pd.Series[Any], right: pd.Series[Any]) -> float:
    """Return chi-squared independence p-value for categorical pairs."""
    table = pd.crosstab(
        left.astype("string").fillna("<missing>"), right.astype("string").fillna("<missing>")
    )
    if table.shape[0] < 2 or table.shape[1] < 2:
        return 1.0
    _, p_value, _, _ = chi2_contingency(table)
    return float(p_value)


def _hsic_p_value(left: pd.Series[Any], right: pd.Series[Any]) -> float:
    """Return HSIC p-value for continuous pairs, with correlation fallback."""
    x = left.to_numpy(dtype=float).reshape(-1, 1)
    y = right.to_numpy(dtype=float).reshape(-1, 1)
    try:
        from hyppo.independence import Hsic  # type: ignore[import-untyped]

        _, p_value = Hsic().test(x, y, reps=100, auto=True)
        return float(p_value)
    except Exception:
        corr = abs(float(np.corrcoef(x[:, 0], y[:, 0])[0, 1]))
        return 0.0 if corr > 0.75 else 1.0


def _mutual_information_p_value(left: pd.Series[Any], right: pd.Series[Any]) -> float:
    """Return a bounded pseudo p-value from binned mutual information."""
    left_codes = _codes(left)
    right_codes = _codes(right)
    table = pd.crosstab(left_codes, right_codes)
    total = float(table.to_numpy().sum())
    if total == 0.0 or table.shape[0] < 2 or table.shape[1] < 2:
        return 1.0
    joint = table.to_numpy(dtype=float) / total
    px = joint.sum(axis=1, keepdims=True)
    py = joint.sum(axis=0, keepdims=True)
    expected = px @ py
    mask = joint > 0
    mi = float((joint[mask] * np.log(joint[mask] / expected[mask])).sum())
    return float(np.exp(-mi))


def _codes(series: pd.Series[Any]) -> np.ndarray[Any, Any]:
    """Return stable integer codes for a mixed-type series."""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() >= max(5, int(0.8 * len(series))):
        return pd.qcut(
            numeric.fillna(numeric.median()), q=4, duplicates="drop"
        ).cat.codes.to_numpy()
    codes, _ = pd.factorize(series.astype("string").fillna("<missing>"), sort=True)
    return codes


def _try_add_edge(
    dag: CausalDAG,
    source: str,
    target: str,
    *,
    confidence: float,
    provenance: str,
    warnings: list[str],
) -> None:
    """Add an edge or record the cycle warning."""
    try:
        dag.add_edge(source, target, confidence=confidence, provenance=provenance)
    except ValueError as exc:
        warnings.append(str(exc))

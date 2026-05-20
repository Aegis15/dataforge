"""Unit tests for causal DAG discovery and root-cause analysis."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from dataforge.causal import pc as pc_module
from dataforge.causal.dag import CausalDAG
from dataforge.causal.pc import discover_causal_dag
from dataforge.causal.root_cause import CausalRootCauseAnalyzer, ErrorEvidence
from dataforge.verifier.schema import FunctionalDependency, Schema

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "cascading"


def test_dag_reachability_and_cycle_rejection() -> None:
    """CausalDAG exposes reachability and rejects cycles."""
    dag = CausalDAG(["discount_pct", "order_total", "invoice_total"])
    dag.add_edge("discount_pct", "order_total", confidence=0.9, provenance="test")
    dag.add_edge("order_total", "invoice_total", confidence=0.8, provenance="test")

    assert dag.is_reachable("discount_pct", "invoice_total") is True
    assert dag.path_confidence("discount_pct", "invoice_total") == 0.8

    try:
        dag.add_edge("invoice_total", "discount_pct", confidence=0.5, provenance="test")
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected cycle rejection")


def test_dag_metadata_absent_paths_and_root_deduplication() -> None:
    """DAG utilities clamp metadata and handle absent nodes deterministically."""
    dag = CausalDAG(["source"])
    dag.add_node("target")
    dag.add_edge("source", "target", confidence=1.5, provenance="manual")

    assert dag.nodes == ("source", "target")
    assert dag.edges[0].confidence == 1.0
    assert dag.edges[0].provenance == "manual"
    assert dag.successors("missing") == ()
    assert dag.is_reachable("missing", "target") is False
    assert dag.path_confidence("missing", "target") == 0.0
    assert dag.minimal_root_columns(["source", "target", "source"]) == ("source",)

    with pytest.raises(ValueError, match="self-edges"):
        dag.add_edge("source", "source", confidence=0.5, provenance="bad")


def test_fd_priors_seed_edges() -> None:
    """Functional dependencies become high-confidence prior edges."""
    df = pd.DataFrame(
        {
            "zip_code": ["10001", "10001", "90210", "90210"],
            "city": ["NY", "NY", "LA", "LA"],
        }
    )
    schema = Schema(
        functional_dependencies=[FunctionalDependency(determinant=("zip_code",), dependent="city")]
    )

    result = discover_causal_dag(df, schema)

    assert result.dag.is_reachable("zip_code", "city")
    assert result.confidence_report["zip_code->city"] == 0.95


def test_discovery_reports_cycle_warnings_for_conflicting_fd_priors() -> None:
    """Conflicting FD priors do not crash discovery; they are reported."""
    df = pd.DataFrame({"a": ["x", "y", "z"], "b": ["u", "v", "w"]})
    schema = Schema(
        functional_dependencies=[
            FunctionalDependency(determinant=("a",), dependent="b"),
            FunctionalDependency(determinant=("b",), dependent="a"),
        ]
    )

    result = discover_causal_dag(df, schema)

    assert result.dag.is_reachable("a", "b")
    assert any("cycle" in warning for warning in result.warnings)


def test_pc_dependency_helpers_cover_categorical_numeric_and_import_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Low-level PC helpers return bounded values under fallback paths."""
    constant = pd.Series(["same", "same", "same", "same"])
    numeric = pd.Series([1, 2, 3, 4, 5, 6])
    correlated = pd.Series([2, 4, 6, 8, 10, 12])
    mixed = pd.Series(["a", "a", "b", "b", "c", "c"])

    assert pc_module._chi_squared_p_value(constant, constant) == 1.0
    assert 0.0 <= pc_module._mutual_information_p_value(numeric, mixed) <= 1.0
    assert pc_module._codes(numeric).shape == (6,)

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "hyppo.independence":
            raise ImportError("blocked for fallback coverage")
        if name == "causallearn.search.ConstraintBased.PC":
            raise ImportError("blocked for fallback coverage")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert pc_module._hsic_p_value(numeric, correlated) == 0.0
    assert pc_module._run_causal_learn_pc(numeric.to_numpy().reshape(-1, 1), ["x"], 0.05)[
        1
    ].startswith("causal-learn PC unavailable")


def test_minimal_root_set_for_chain() -> None:
    """The minimal root is the selected upstream error."""
    dag = CausalDAG(["quantity", "order_total", "invoice_total"])
    dag.add_edge("quantity", "order_total", confidence=0.9, provenance="test")
    dag.add_edge("order_total", "invoice_total", confidence=0.8, provenance="test")
    errors = [
        ErrorEvidence(index=0, row=4, column="quantity", issue_type="decimal_shift"),
        ErrorEvidence(index=1, row=4, column="order_total", issue_type="formula"),
        ErrorEvidence(index=2, row=4, column="invoice_total", issue_type="formula"),
    ]

    result = CausalRootCauseAnalyzer(dag).analyze(errors)

    assert result.root_indices == [0]
    assert result.covered_indices == [0, 1, 2]
    assert result.confidence > 0.0


def test_missing_upstream_error_becomes_local_root() -> None:
    """When the upstream error is absent, the earliest selected downstream error roots."""
    dag = CausalDAG(["quantity", "order_total", "invoice_total"])
    dag.add_edge("quantity", "order_total", confidence=0.9, provenance="test")
    dag.add_edge("order_total", "invoice_total", confidence=0.8, provenance="test")
    errors = [
        ErrorEvidence(index=3, row=4, column="order_total", issue_type="formula"),
        ErrorEvidence(index=4, row=4, column="invoice_total", issue_type="formula"),
    ]

    result = CausalRootCauseAnalyzer(dag).analyze(errors)

    assert result.root_indices == [3]


def test_cascading_fixture_precision_recall() -> None:
    """Committed cascading fixtures identify roots above the Week 10 threshold."""
    true_positive = 0
    predicted_count = 0
    truth_count = 0

    for meta_path in sorted(FIXTURE_DIR.glob("case_*.json")):
        csv_path = meta_path.with_suffix(".csv")
        metadata: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        pd.read_csv(csv_path)

        dag = CausalDAG(metadata["columns"])
        for edge in metadata["edges"]:
            dag.add_edge(
                edge["source"],
                edge["target"],
                confidence=edge["confidence"],
                provenance=edge["provenance"],
            )
        errors = [ErrorEvidence(**error) for error in metadata["errors"]]
        predicted = set(CausalRootCauseAnalyzer(dag).analyze(errors).root_indices)
        truth = set(metadata["root_indices"])

        true_positive += len(predicted & truth)
        predicted_count += len(predicted)
        truth_count += len(truth)

    precision = true_positive / predicted_count
    recall = true_positive / truth_count

    assert precision >= 0.85
    assert recall >= 0.90

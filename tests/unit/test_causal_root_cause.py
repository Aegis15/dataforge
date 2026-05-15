"""Unit tests for causal DAG discovery and root-cause analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

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

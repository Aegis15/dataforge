"""Unit tests for benchmark report helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataforge.bench.report import (
    build_readme_benchmark_block,
    load_agent_output,
    load_sota_output,
    render_benchmark_report,
    replace_benchmark_block,
    write_benchmark_outputs,
)
from scripts.bench.run_sota_comparison import build_sota_payload

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "bench"


class TestReportHelpers:
    """Report rendering and README block updates."""

    def test_replace_benchmark_block_requires_markers(self) -> None:
        with pytest.raises(ValueError, match="markers"):
            replace_benchmark_block("# DataForge", "new")

    def test_render_report_and_readme_block(self) -> None:
        agent_output = load_agent_output(_FIXTURES / "agent_comparison.json")
        sota_output = load_sota_output(_FIXTURES / "sota_comparison.json")

        report = render_benchmark_report(agent_output, sota_output)
        block = build_readme_benchmark_block(agent_output, Path("BENCHMARK_REPORT.md"))

        assert "Cross-Dataset Local Results" in report
        assert "Citation-Only SOTA Reference" in report
        assert "BENCHMARK_REPORT.md" in block

    def test_write_benchmark_outputs_is_idempotent(self, tmp_path: Path) -> None:
        agent_json = tmp_path / "agent.json"
        sota_json = tmp_path / "sota.json"
        report_path = tmp_path / "BENCHMARK_REPORT.md"
        readme_path = tmp_path / "README.md"
        homepage_path = tmp_path / "docs" / "docs" / "index.md"
        agent_json.write_text(
            (_FIXTURES / "agent_comparison.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        sota_json.write_text(
            (_FIXTURES / "sota_comparison.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        readme_path.write_text(
            "# DataForge\n\n<!-- BENCH:START -->old<!-- BENCH:END -->\n",
            encoding="utf-8",
        )
        homepage_path.parent.mkdir(parents=True, exist_ok=True)
        homepage_path.write_text(
            "# Home\n\n<!-- BENCH:START -->old<!-- BENCH:END -->\n",
            encoding="utf-8",
        )

        write_benchmark_outputs(
            agent_json_path=agent_json,
            sota_json_path=sota_json,
            report_path=report_path,
            readme_path=readme_path,
            homepage_path=homepage_path,
        )
        first_readme = readme_path.read_text(encoding="utf-8")
        first_homepage = homepage_path.read_text(encoding="utf-8")
        write_benchmark_outputs(
            agent_json_path=agent_json,
            sota_json_path=sota_json,
            report_path=report_path,
            readme_path=readme_path,
            homepage_path=homepage_path,
        )

        assert readme_path.read_text(encoding="utf-8") == first_readme
        assert homepage_path.read_text(encoding="utf-8") == first_homepage
        assert "Generated from `eval/results/agent_comparison.json`" in first_homepage

    def test_sota_payload_is_citation_evidence_not_reproduced_rows(self) -> None:
        payload = build_sota_payload()

        assert payload["schema_version"] == "dataforge_sota_citation_v1"
        source = payload["source"]
        assert isinstance(source, dict)
        assert source["title"] == "BClean: A Bayesian Data Cleaning System"
        assert source["url"] == "https://arxiv.org/abs/2311.06517"
        assert len(source["source_sha256"]) == 64
        for row in payload["rows"]:
            assert row["evidence_kind"] == "citation_only"
            assert row["source_title"] == source["title"]

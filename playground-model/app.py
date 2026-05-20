"""Gradio Space for the DataForge-0.5B-SFT warmup checkpoint."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from typing import Any

import gradio as gr

try:
    import spaces
except ImportError:  # pragma: no cover - local development fallback

    class _SpacesFallback:
        """Compatibility shim for non-Space local runs."""

        @staticmethod
        def GPU(  # noqa: N802 - mirrors the Hugging Face spaces API.
            *args: object,
            **kwargs: object,
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            """Return an identity decorator when the HF `spaces` package is absent."""
            del args, kwargs

            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                return func

            return decorator

    spaces = _SpacesFallback()


MODEL_ID = "Praneshrajan15/DataForge-0.5B-SFT"
MAX_ROWS = 50
EXAMPLE_SNIPPETS = [
    "id,amount,department\n1,100,cardiology\n2,105,cardiology\n3,1020,cardiology",
    "id,email,zip\n1,ana@example.com,02139\n2,bob@example.com,2139\n3,chen@example.com,02139",
    "id,room,ward\n1,12A,north\n2,12A,north\n3,99Z,south",
]
TABLE_HEADERS = [
    "status",
    "row",
    "column",
    "issue_type",
    "old_value",
    "new_value",
    "confidence",
    "reason",
]
SYSTEM_PROMPT = (
    "You are DataForge-0.5B-SFT. Given a CSV snippet, return JSON only. "
    "Use either a list of repair objects or {'fixes': [...]} with keys row, "
    "column, issue_type, old_value, new_value, confidence, reason. If no repair "
    "is justified, return an empty list."
)


def _table_row(
    *,
    status: str,
    row: str = "",
    column: str = "",
    issue_type: str = "",
    old_value: str = "",
    new_value: str = "",
    confidence: str = "",
    reason: str = "",
) -> list[str]:
    """Build one stable output-table row."""
    return [status, row, column, issue_type, old_value, new_value, confidence, reason]


def parse_csv_snippet(csv_snippet: str) -> tuple[bool, str, list[dict[str, str]]]:
    """Parse and validate a CSV snippet submitted to the demo.

    Args:
        csv_snippet: Raw CSV text from the Gradio textbox.

    Returns:
        Tuple of `(ok, message, rows)`. When `ok` is false, `message` is safe to
        show in the UI and `rows` is empty.
    """
    if not csv_snippet.strip():
        return False, "Paste a CSV snippet with a header row and up to 50 data rows.", []

    try:
        reader = csv.DictReader(io.StringIO(csv_snippet))
        if reader.fieldnames is None or not any(name for name in reader.fieldnames):
            return False, "CSV must include a header row.", []
        rows = [dict(row) for row in reader]
    except csv.Error as exc:
        return False, f"CSV could not be parsed: {exc}", []

    if not rows:
        return False, "CSV must include at least one data row.", []
    if len(rows) > MAX_ROWS:
        return False, f"CSV snippet has {len(rows)} rows; the demo accepts at most {MAX_ROWS}.", []
    return True, "CSV accepted.", rows


def _json_candidates(text: str) -> list[Any]:
    """Return JSON payload candidates parsed from a model response."""
    stripped = text.strip()
    candidates: list[Any] = []
    for candidate in (stripped, _extract_json_block(stripped)):
        if not candidate:
            continue
        try:
            candidates.append(json.loads(candidate))
        except json.JSONDecodeError:
            continue
    return candidates


def _extract_json_block(text: str) -> str | None:
    """Extract the outermost JSON-looking block from model text."""
    starts = [index for index in (text.find("["), text.find("{")) if index >= 0]
    if not starts:
        return None
    start = min(starts)
    end = max(text.rfind("]"), text.rfind("}"))
    if end <= start:
        return None
    return text[start : end + 1]


def parse_model_output(model_text: str) -> list[list[str]]:
    """Normalize model output into stable table rows."""
    for payload in _json_candidates(model_text):
        raw_items: Any
        if isinstance(payload, dict):
            raw_items = payload.get("fixes", payload.get("issues", []))
        else:
            raw_items = payload
        if not isinstance(raw_items, list):
            continue
        rows: list[list[str]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            rows.append(
                _table_row(
                    status="proposed",
                    row=str(item.get("row", "")),
                    column=str(item.get("column", "")),
                    issue_type=str(item.get("issue_type", item.get("detector_id", ""))),
                    old_value=str(item.get("old_value", item.get("actual", ""))),
                    new_value=str(item.get("new_value", item.get("expected", ""))),
                    confidence=str(item.get("confidence", "")),
                    reason=str(item.get("reason", "")),
                )
            )
        return rows or [_table_row(status="ok", reason="The model returned no proposed fixes.")]
    preview = model_text.strip().replace("\n", " ")
    if len(preview) > 240:
        preview = preview[:237] + "..."
    return [_table_row(status="raw", reason=preview or "The model returned an empty response.")]


def _build_prompt(csv_snippet: str) -> str:
    """Build the instruction prompt sent to the model."""
    return f"{SYSTEM_PROMPT}\n\nCSV:\n{csv_snippet.strip()}\n\nJSON:"


def _generate_model_text(csv_snippet: str) -> str:
    """Run the Hub model and return decoded text."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model_kwargs: dict[str, Any] = {}
    if torch.cuda.is_available():
        model_kwargs["torch_dtype"] = torch.float16
        model_kwargs["device_map"] = "auto"
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, **model_kwargs)
    if not torch.cuda.is_available():
        model = model.to("cpu")

    prompt = _build_prompt(csv_snippet)
    inputs = tokenizer(prompt, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {key: value.to(device) for key, value in inputs.items()}
    outputs = model.generate(
        **inputs,
        max_new_tokens=384,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )
    generated = outputs[0][inputs["input_ids"].shape[-1] :]
    text = tokenizer.decode(generated, skip_special_tokens=True)

    del model
    del tokenizer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return str(text)


@spaces.GPU(duration=60)
def detect_and_propose(csv_snippet: str) -> list[list[str]]:
    """Detect data-quality issues and propose fixes for a CSV snippet."""
    ok, message, _rows = parse_csv_snippet(csv_snippet)
    if not ok:
        return [_table_row(status="error", reason=message)]
    try:
        model_text = _generate_model_text(csv_snippet)
    except Exception as exc:
        return [_table_row(status="error", reason=f"Model inference failed: {exc}")]
    return parse_model_output(model_text)


def detect_and_propose_with_status(csv_snippet: str) -> tuple[list[list[str]], str]:
    """Return model proposals plus an honest demo-status message."""
    rows = detect_and_propose(csv_snippet)
    first_status = rows[0][0] if rows else "raw"
    if first_status == "error":
        return rows, "Input rejected or inference failed. The verified playground path remains Profile -> Repair -> Verify -> Revert."
    if first_status == "raw":
        return rows, "The checkpoint returned unstructured text. Treat this as research output, not a verified repair."
    if first_status == "ok":
        return rows, "The checkpoint proposed no fixes for this snippet."
    return rows, f"Experimental checkpoint returned {len(rows)} proposed fix row(s). Verify repairs with the CLI or playground API before trusting them."


with gr.Blocks(title="DataForge 0.5B SFT") as demo:
    gr.Markdown(
        """
# DataForge 0.5B SFT

Experimental model demo for short CSV snippets. This Space shows what the warmup
checkpoint proposes; it does not apply repairs, store data, or replace the
verified DataForge workflow.

**Use the product path for evidence:** Profile -> Repair -> Verify -> Revert
in the CLI or Cloudflare playground. This model surface is intentionally bounded
to 50 rows, one queued inference at a time, and research-grade outputs.
"""
    )
    with gr.Row():
        with gr.Column(scale=2):
            csv_input = gr.Textbox(
                label="CSV snippet",
                lines=14,
                max_lines=20,
                placeholder="id,amount\n1,100\n2,105\n3,1020",
            )
            gr.Examples(
                examples=EXAMPLE_SNIPPETS,
                inputs=csv_input,
                label="Audited examples",
            )
            run_button = gr.Button("Detect + propose fixes", variant="primary")
        with gr.Column(scale=3):
            output = gr.Dataframe(
                headers=TABLE_HEADERS,
                datatype=["str"] * len(TABLE_HEADERS),
                row_count=1,
                column_count=len(TABLE_HEADERS),
                label="Model output",
            )
            status_output = gr.Markdown("Waiting for a CSV snippet.")
    run_button.click(
        detect_and_propose_with_status,
        inputs=csv_input,
        outputs=[output, status_output],
        show_progress="full",
        concurrency_limit=1,
    )

demo.queue(max_size=8, default_concurrency_limit=1)


if __name__ == "__main__":
    demo.launch()

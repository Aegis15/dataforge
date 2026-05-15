"""Contract tests for the Kaggle SFT warmup notebook and YAML config."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "training" / "kaggle" / "sft_warmup_kaggle.ipynb"
CONFIG = ROOT / "training" / "configs" / "sft_05b.yaml"


def _notebook_source() -> str:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", ""))
        for cell in payload["cells"]
        if cell.get("cell_type") == "code"
    )


def test_config_owns_training_hyperparameters_and_exact_package_pins() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    assert config["model"]["base_model"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert config["training"]["fp16"] is True
    assert config["training"]["bf16"] is False
    assert config["training"]["save_steps"] == 100
    assert config["training"]["per_device_train_batch_size"] == 1
    assert config["training"]["gradient_accumulation_steps"] == 16
    assert config["training"]["max_seq_length"] == 1024
    assert config["training"]["loss_type"] == "chunked_nll"
    assert "trl==1.4.0" in config["environment"]["pip_packages"]
    assert config["lora"]["target_modules"] == ["q_proj", "k_proj", "v_proj", "o_proj"]
    assert config["evaluation"]["chunk_width"] == 4
    assert config["evaluation"]["max_new_tokens"] == 1024
    assert config["collection"]["oracle"]["include_noop_records"] is True
    assert all("==" in package for package in config["environment"]["pip_packages"])


def test_notebook_has_six_main_cells_and_no_placeholder_owner() -> None:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    main_cells = [
        cell
        for cell in payload["cells"]
        if cell.get("cell_type") == "code"
        and "week9_main" in cell.get("metadata", {}).get("tags", [])
    ]
    source = _notebook_source()

    assert len(main_cells) == 6
    assert "<you>" not in source
    assert "bf16=True" not in source
    assert '"pending"' not in source
    assert "kaggle_secrets" in source
    assert 'secrets.get_secret("HF_TOKEN")' in source
    assert 'os.environ["HF_TOKEN"] = HF_TOKEN' in source
    assert 'os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN' in source
    assert '"pip", "uninstall", "-y", "torchao"' in source
    assert "torchao: not installed" in source


def test_notebook_loads_yaml_and_exercises_required_training_flow() -> None:
    source = _notebook_source()

    assert "yaml.safe_load" in source
    assert "hf_hub_download" in source
    assert "BitsAndBytesConfig" in source
    assert "LoraConfig" in source
    assert "SFTTrainer" in source
    assert "expected_t4_training" in source
    assert "Downloaded sft_05b.yaml is stale for this T4 run" in source
    assert 'loss_type=train_cfg["loss_type"]' in source
    assert "Loaded T4 training memory settings:" in source
    assert "Installed TRL does not support loss_type='chunked_nll'" in source
    assert 'importlib_metadata.version("trl")' in source
    assert 'device_map={"": 0}' in source
    assert "Trainable parameter dtypes:" in source
    assert "bf16 trainable parameters remain" in source
    assert "param.dtype != torch.float32" in source
    assert "latest_checkpoint = None" in source
    assert "resume_from_checkpoint=latest_checkpoint" in source
    assert "merge_and_unload" in source
    assert "training_metrics.json" in source
    assert "evaluate_model(" in source
    assert "torch.cuda.empty_cache()" in source
    assert source.count("api.upload_folder(") == 1
    assert "collection_methods" in source
    assert "oracle_from_clean_diff" in source
    assert "accepted_teachers" in source
    assert "parse_json_payload" in source
    assert "submit_repairs" in source
    assert "chunk_width" in source
    assert "split_manifest.json" in source
    assert "validate_split_manifest" in source
    assert "DATASET_SHA" in source
    assert '"dataset_sha": DATASET_SHA' in source
    assert "base_eval" in source
    assert "sft_eval" in source
    assert '"macro_f1"' in source
    assert "quality_milestone" in source
    assert "pipeline_complete_no_heldout_gain" in source
    assert '"dataset": dataset_name' in source
    assert (
        'dataset_name = task.get("dataset") or task.get("schema_summary", {}).get("dataset", "unknown")'
        in source
    )
    assert 'task_scores.append({"dataset": dataset_name' in source

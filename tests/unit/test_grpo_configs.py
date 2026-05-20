"""Contract tests for Week 12 GRPO training configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from training.grpo_config import GrpoConfigError, build_grpo_config_kwargs, load_grpo_config

ROOT = Path(__file__).resolve().parents[2]
CONFIG_05B = ROOT / "training" / "configs" / "grpo_05b.yaml"
CONFIG_15B = ROOT / "training" / "configs" / "grpo_15b.yaml"


def test_grpo_05b_config_uses_supported_v1_stack_and_free_tier_hparams() -> None:
    """The 0.5B GRPO config should encode the corrected Week 12 defaults."""
    config = load_grpo_config(CONFIG_05B)

    packages = config["environment"]["pip_packages"]
    assert "trl==1.4.0" in packages
    assert all("==0.11" not in package for package in packages)
    assert "tensorboard==2.20.0" in packages
    assert config["model"]["sft_checkpoint"] == "Praneshrajan15/DataForge-0.5B-SFT"
    assert config["model"]["target_model_repo"].endswith("/DataForge-0.5B-GRPO")
    assert config["lora"]["r"] == 16
    assert config["training"]["fp16"] is True
    assert config["training"]["bf16"] is False
    assert config["training"]["num_generations"] == 4
    assert config["training"]["prompt_token_budget"] == 1024
    assert config["training"]["max_completion_length"] == 256
    assert config["training"]["per_device_train_batch_size"] == 1
    assert config["training"]["gradient_accumulation_steps"] == 16
    assert config["training"]["beta"] == 0.04
    assert config["training"]["learning_rate"] == pytest.approx(1e-5)
    assert config["training"]["num_iterations"] == 1
    assert config["training"]["save_steps"] == 50
    assert config["training"]["logging_steps"] == 5
    assert config["training"]["report_to"] == "tensorboard"
    assert config["release"]["min_absolute_f1_gain"] == pytest.approx(0.03)
    assert config["release"]["benchmark_seeds"] == [0, 1, 2]


def test_grpo_15b_config_requires_sft_warmup_and_qlora() -> None:
    """The 1.5B config must not silently start from a raw base model."""
    config = load_grpo_config(CONFIG_15B)

    assert config["model"]["sft_checkpoint"] == "Praneshrajan15/DataForge-1.5B-SFT"
    assert config["model"]["sft_checkpoint_required"] is True
    assert config["model"]["target_model_repo"].endswith("/DataForge-1.5B-GRPO")
    assert config["lora"]["r"] == 8
    assert config["quantization"]["load_in_4bit"] is True
    assert config["quantization"]["bnb_4bit_quant_type"] == "nf4"
    assert config["training"]["gradient_checkpointing"] is True
    assert config["training"]["use_cache"] is False
    assert config["training"]["num_generations"] == 4


def test_grpo_kwargs_map_prompt_budget_only_when_trl_supports_it() -> None:
    """`max_prompt_length` is optional because current local TRL lacks it."""
    config = load_grpo_config(CONFIG_05B)
    supported = {
        "output_dir",
        "num_generations",
        "max_completion_length",
        "per_device_train_batch_size",
        "gradient_accumulation_steps",
        "beta",
        "learning_rate",
        "num_iterations",
        "save_steps",
        "logging_steps",
        "report_to",
        "fp16",
        "bf16",
    }

    kwargs = build_grpo_config_kwargs(config, supported_keys=supported)

    assert kwargs["num_generations"] == 4
    assert kwargs["max_completion_length"] == 256
    assert "prompt_token_budget" not in kwargs
    assert "max_prompt_length" not in kwargs

    supported_with_prompt = set(supported) | {"max_prompt_length"}
    kwargs_with_prompt = build_grpo_config_kwargs(config, supported_keys=supported_with_prompt)
    assert kwargs_with_prompt["max_prompt_length"] == 1024


def test_grpo_config_loader_rejects_stale_trl_011(tmp_path: Path) -> None:
    """The corrected plan must fail fast on the stale TRL v0.11 assumption."""
    config = yaml.safe_load(CONFIG_05B.read_text(encoding="utf-8"))
    config["environment"]["pip_packages"] = ["trl==0.11.0", "transformers==5.7.0"]
    path = tmp_path / "bad_grpo.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(GrpoConfigError, match="TRL v0.11"):
        load_grpo_config(path)

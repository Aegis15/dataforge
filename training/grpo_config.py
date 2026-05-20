"""Helpers for loading and adapting Week 12 GRPO YAML configs."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REQUIRED_PIP_PACKAGES = {
    "trl==1.4.0",
    "transformers==5.7.0",
    "accelerate==1.13.0",
    "peft==0.19.1",
    "bitsandbytes==0.49.2",
    "datasets==4.8.5",
    "huggingface_hub==1.13.0",
    "pyyaml==6.0.3",
    "pandas==2.3.3",
    "tensorboard==2.20.0",
}

REQUIRED_TRAINING_VALUES: dict[str, object] = {
    "num_generations": 4,
    "max_completion_length": 256,
    "prompt_token_budget": 1024,
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 16,
    "beta": 0.04,
    "learning_rate": 1e-5,
    "num_iterations": 1,
    "save_steps": 50,
    "logging_steps": 5,
    "report_to": "tensorboard",
    "fp16": True,
    "bf16": False,
}

PASSTHROUGH_TRAINING_KEYS = {
    "output_dir",
    "per_device_train_batch_size",
    "learning_rate",
    "gradient_accumulation_steps",
    "bf16",
    "fp16",
    "gradient_checkpointing",
    "report_to",
    "save_steps",
    "logging_steps",
    "num_generations",
    "max_completion_length",
    "beta",
    "num_iterations",
    "max_steps",
    "warmup_ratio",
    "lr_scheduler_type",
    "weight_decay",
    "save_total_limit",
    "use_cache",
}


class GrpoConfigError(RuntimeError):
    """Raised when a GRPO handoff config is unsafe or stale."""


def _as_mapping(value: object, *, name: str) -> dict[str, Any]:
    """Return a YAML object as a string-keyed mapping."""
    if not isinstance(value, dict):
        raise GrpoConfigError(f"{name} must be a mapping.")
    return dict(value)


def load_grpo_config(path: Path) -> dict[str, Any]:
    """Load and validate a Week 12 GRPO YAML config."""
    if not path.exists():
        raise GrpoConfigError(f"Missing GRPO config: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = _as_mapping(payload, name=str(path))
    for section in ("environment", "repos", "model", "lora", "training", "reward", "release"):
        if section not in config:
            raise GrpoConfigError(f"GRPO config is missing required section: {section}")

    environment = _as_mapping(config["environment"], name="environment")
    packages = environment.get("pip_packages")
    if not isinstance(packages, list) or not all(isinstance(item, str) for item in packages):
        raise GrpoConfigError("environment.pip_packages must be a list of exact package pins.")
    unpinned = [package for package in packages if "==" not in package]
    if unpinned:
        raise GrpoConfigError("GRPO package pins must be exact: " + ", ".join(unpinned))
    if any(package.startswith("trl==0.11") for package in packages):
        raise GrpoConfigError("TRL v0.11 does not provide the required GRPOTrainer path.")
    missing = sorted(REQUIRED_PIP_PACKAGES - set(packages))
    if missing:
        raise GrpoConfigError("GRPO config missing package pin(s): " + ", ".join(missing))

    training = _as_mapping(config["training"], name="training")
    stale = {
        key: training.get(key)
        for key, expected in REQUIRED_TRAINING_VALUES.items()
        if training.get(key) != expected
    }
    if stale:
        raise GrpoConfigError(f"GRPO training settings are stale or unsafe: {stale}")
    if "max_prompt_length" in training:
        raise GrpoConfigError("Use training.prompt_token_budget instead of max_prompt_length.")

    release = _as_mapping(config["release"], name="release")
    if release.get("benchmark_name") != "DataForge-Bench-light-verified":
        raise GrpoConfigError("release.benchmark_name must be DataForge-Bench-light-verified.")
    if float(release.get("min_absolute_f1_gain", 0.0)) < 0.03:
        raise GrpoConfigError("release.min_absolute_f1_gain must be at least 0.03.")
    if release.get("benchmark_seeds") != [0, 1, 2]:
        raise GrpoConfigError("release.benchmark_seeds must be [0, 1, 2].")
    return config


def build_grpo_config_kwargs(
    config: dict[str, Any],
    *,
    supported_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Build kwargs safe to pass to TRL's ``GRPOConfig``.

    ``prompt_token_budget`` is a DataForge-local tokenizer constraint. It is
    mapped to ``max_prompt_length`` only for TRL versions that expose that
    parameter.
    """
    training = _as_mapping(config["training"], name="training")
    if supported_keys is None:
        supported_keys = installed_grpo_config_keys()
    kwargs: dict[str, Any] = {}
    for key in PASSTHROUGH_TRAINING_KEYS:
        if key in training and key in supported_keys:
            kwargs[key] = training[key]
    if "max_prompt_length" in supported_keys:
        kwargs["max_prompt_length"] = training["prompt_token_budget"]
    return kwargs


def installed_grpo_config_keys() -> set[str]:
    """Return the parameter names exposed by the installed TRL ``GRPOConfig``."""
    from trl import GRPOConfig

    return set(inspect.signature(GRPOConfig).parameters)


def run_grpo_import_preflight(python_executable: Path | None = None) -> None:
    """Verify ``GRPOTrainer`` imports under UTF-8 mode before launching Kaggle.

    Some Windows environments fail on TRL chat-template reads unless UTF-8 mode
    is enabled. The notebook mirrors this by setting ``PYTHONUTF8=1`` before
    importing TRL.
    """
    executable = str(python_executable or Path(sys.executable))
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    command = [
        executable,
        "-c",
        "from trl import GRPOConfig, GRPOTrainer; print('grpo-ok')",
    ]
    subprocess.run(command, check=True, capture_output=True, text=True, env=env, timeout=120)

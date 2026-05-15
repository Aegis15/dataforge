---
title: DataForge 0.5B SFT
sdk: gradio
app_file: app.py
license: apache-2.0
models:
  - Praneshrajan15/DataForge-0.5B-SFT
tags:
  - data-quality
  - tabular-data
  - gradio
  - zerogpu
---

# DataForge 0.5B SFT

This Space demos `Praneshrajan15/DataForge-0.5B-SFT`, a Week 9 supervised
fine-tuning warmup checkpoint for DataForge-style tabular repair traces.

Paste a CSV snippet with a header row and up to 50 data rows, then run
**Detect + propose fixes**. The model returns proposed issue/fix rows when it
can parse the task. The checkpoint is currently evidence that the DataForge
training, merge, evaluation, and publish path works; it is not a production
quality claim.

## ZeroGPU setup

Create a Hugging Face Space with the Gradio SDK and select ZeroGPU in the Space
settings. Hugging Face's current ZeroGPU documentation describes Gradio-only
dynamic GPU allocation backed by shared RTX Pro 6000 Blackwell capacity. Queue
priority and daily quota depend on the visitor's account tier, so public demo
calls can occasionally wait or fail when quota is exhausted.

The Space loads model weights from the Hugging Face Hub with
`from_pretrained()`. Model weights, generated caches, and user CSV snippets are
not committed to this repository.

## Limitations

- Inputs are capped at 50 rows to keep public calls bounded.
- The model may emit malformed JSON or propose incorrect fixes.
- Do not use this demo for autonomous production data modification.
- Run real DataForge repairs through the CLI or MCP server so safety,
  verification, and transaction logging remain in the loop.


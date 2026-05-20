# Safety Concept

Safety is the write gate between a proposed repair and a mutated file. The
system treats every fix as untrusted until it passes policy checks and formal
verification.

## Layers

- Constitution rules reject dangerous edits such as row deletion and unsafe PII
  overwrites.
- Batch checks reject conflicting writes.
- Repairers attach provenance and confidence so reviewers can distinguish
  deterministic proposals from escalations.
- The SMT verifier checks schema-level constraints before mutation.

## Failure behavior

If safety or verification cannot run, applied repair paths fail closed. Dry-run
paths can still show proposed work, but a failed gate prevents mutation.

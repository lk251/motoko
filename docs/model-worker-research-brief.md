# Motoko Worker Model Research Brief

This brief is for NixOS-side work in `/home/javier/repos/nixos-configs`.
Motoko already has named model routes; NixOS should decide which local services
and models back those routes.

## Goal

Find local, resource-efficient worker models that can handle repetitive
background tasks without making the main chat model do every call. Keep the
large model available for final synthesis, ambiguous reasoning, audits, and
chat.

HB3 currently has one RTX 4090 with about 24 GiB VRAM. Model residency and
switching cost matter. Prefer service layouts that avoid loading and unloading
models during active chat unless measurements show the cost is acceptable.

## Motoko Routes

- `chat`: interactive answers and final user-facing synthesis. Keep on the
  strongest local chat model.
- `index_chunk`: chunk summaries. Candidate small-model route.
- `index_file`: file summaries, file-purpose maps, and lightweight
  classification. Candidate small-model route.
- `index_label`: file/document labels, lightweight classification, and routing
  hints. Candidate small-model or classifier route.
- `index_corpus`: corpus-level synthesis across many file summaries. Usually a
  stronger or larger route than chunk/file summaries.
- `topic`: topic and deep dossiers over retrieved evidence. Stronger route.
- `memory`: conversation compaction and query-focused memory dossiers. Stronger
  route unless a smaller model passes quality gates.
- `profile`: profile dossier synthesis. Stronger route.
- `title`: short titles and labels. Candidate small-model route.
- `audit`: rare quality audits and reflective checks. Strong route.

## Required Competence

Worker candidates should be evaluated for:

- faithful compression without invented facts;
- preservation of names, dates, deadlines, TODO states, priorities,
  obligations, project names, file paths, and unusual details;
- strong performance on Org-mode notes, Markdown/plain text, source/config
  files, and mixed personal planning documents;
- ability to produce compact summaries from 8k-16k input contexts;
- low refusal/roleplay behavior for private local notes;
- stable output under low temperature;
- good llama.cpp support, quantization quality, and predictable VRAM use;
- useful speed when called many times in a long background indexing job.

## Evaluation Bar

Do not route a task to a smaller model solely because it is faster. It must pass
Motoko's synthetic quality gate: task-priority retrieval should preserve names,
dates, priorities, obligations, project/file references, source paths, and
answer quality at least as well as the current default route on fixtures.
After the worker services are installed and route variables are configured, run
`motoko model-eval` to score chunk, file, label/classification, and corpus
fixtures. Use `motoko model-eval --write` to save a private JSON report under
Motoko state for comparison between model candidates.

The first useful candidates are likely 3B-8B instruction or
summarization-strong models for `index_chunk`, `index_file`, `index_label`, and
`title`. `index_corpus`, `topic`, `memory`, `profile`, and `audit` should stay
on the larger model until a worker proves itself.

## Candidate Selection Notes

Prefer the newest suitable local worker generation, but verify the actual model
catalog at install time. As of 2026-05-19, the official Qwen3.6 collection
publishes large 27B and 35B-A3B models; it does not appear to publish official
small 0.8B, 2B, 4B, or 9B worker equivalents. The earlier small-worker
candidates are therefore still useful candidates, not permanent pins:

- `Qwen/Qwen3.5-2B` for `index_chunk`;
- `Qwen/Qwen3-4B-Instruct-2507` for `index_file` and quality fallback;
- `Qwen/Qwen3.5-9B` for `index_corpus`;
- `mistralai/Ministral-3-3B-Instruct-2512` for `index_label` and structured
  classification comparison.

If official Qwen3.6 small workers, better Qwen3.x small instruct models, or
better llama.cpp-compatible GGUF quantizations appear before installation, use
those as challengers instead of treating the list above as fixed. The deciding
factor is not the generation number alone; it is whether the model passes
Motoko's route-specific evals with better faithfulness, JSON hygiene, latency,
VRAM use, and joules per artifact.

## Caching

Motoko caches deterministic model outputs for repeatable summary routes in
private state. This is not the same as server-side prompt/KV caching.

NixOS-side research should separately check whether the chosen llama.cpp
service shape can use prompt-prefix or KV reuse safely, and whether that
improves long-prompt background work without hurting chat latency or model
residency.

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

The first useful candidates are likely 3B-8B instruction or summarization-strong
models for `index_chunk`, `index_file`, and `title`. `index_corpus`, `topic`,
`memory`, `profile`, and `audit` should stay on the larger model until a worker
proves itself.

## Caching

Motoko caches deterministic model outputs for repeatable summary routes in
private state. This is not the same as server-side prompt/KV caching.

NixOS-side research should separately check whether the chosen llama.cpp
service shape can use prompt-prefix or KV reuse safely, and whether that
improves long-prompt background work without hurting chat latency or model
residency.

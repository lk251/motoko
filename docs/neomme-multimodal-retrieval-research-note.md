# NeoMME and Deferred Multimodal Retrieval

Date: 2026-09-07
Status: research note; visual retrieval is not a current implementation priority

This note records findings from Lac and Wu (2026), *NeoMME: A Single-Tower
Multimodal-Native Multilingual Foundation Encoder for Efficient Fine-Tuning and
Inference* (arXiv:2609.01657), together with the H Company technical write-up,
and evaluates what is worth preserving for Motoko's retrieval roadmap.

NeoMME is relevant even though image/visual retrieval is not currently a Motoko
priority. Its most useful near-term lesson is architectural rather than visual:
one encoder can emit both a compact dense representation and a fine-grained
late-interaction representation in one forward pass. That maps naturally onto
Motoko's existing direction of cheap candidate generation followed by more
precise reranking. The visual-document capability should remain a deferred lane
for cases where page layout, tables, plots, diagrams, typography, or other
non-textual evidence matter.

Related Motoko documents:

- `docs/retrieval-pipeline-directions.md`
- `docs/project-context.md`
- `docs/deferred-projects.md`
- `docs/selective-forgetting-memory-research-note.md`

## What NeoMME is

NeoMME is a family of 260M- and 800M-parameter multilingual, multimodal,
bidirectional encoders. Unlike common visual-language retrieval architectures,
it does not combine a separately pretrained vision tower with a causal language
model. Text tokens and raw image patches enter one shared bidirectional
Transformer.

The released models support a 16,384-token context. Images are split into
32 x 32 patches and can retain dynamic resolution and aspect ratio, allowing
more representational capacity for information-dense pages.

NeoMME is pretrained from scratch using a masked discrete-diffusion text
objective. In multimodal examples, image patches remain visible while portions
of the text are masked. High masking rates reduce language-only shortcuts and
force the encoder to rely on visible image evidence.

For retrieval, NeoMME-Retriever adds two jointly trained heads:

1. **Dense head:** mean-pools the encoder state into one normalized vector per
   query/document. This is suitable for cheap approximate-nearest-neighbor
   candidate generation.
2. **Late-interaction head:** emits a normalized 128-dimensional vector for each
   text token or image patch. Query/document scoring keeps these local
   representations separate and uses fine-grained matching rather than
   collapsing the document to one vector.

A single model forward pass returns both representations.

## Reported retrieval results

On ViDoRe v3, NeoMME-Retriever-260M reports 0.523 nDCG@10 and the 800M model
0.556. The 260M model is reported as the strongest evaluated model below 800M
parameters on that benchmark. At matched 2048 x 2048 image resolution on an
NVIDIA L40S, the 260M model encodes about 51 pages/second, roughly twice the
reported ColModernVBERT throughput.

The more interesting systems result concerns late-interaction storage.
High-resolution pages produce thousands of patch vectors and therefore large
indexes. The authors combine:

- hierarchical token pooling, which clusters similar document vectors and
  replaces clusters with their mean;
- asymmetric quantization, keeping query vectors at higher precision while
  compressing stored document vectors more aggressively.

They report reducing the average late-interaction representation from roughly
1.5 MB/page to 39 kB/page with more than 99% of baseline retrieval quality in
one configuration, and to about 6 kB/page (255x smaller) while retaining more
than 95% of baseline nDCG@10 in a more aggressive configuration.

These results are benchmark-specific and should not be assumed to transfer
unchanged to Motoko's corpora, but the quality/storage frontier is highly
relevant to any future fine-grained retrieval index.

## Relevance to Motoko now

### 1. Reinforces dense-first, late-interaction-second retrieval

Motoko already treats retrieval as a multi-stage evidence pipeline rather than
a single vector search. NeoMME provides a concrete modern example of an
especially clean implementation pattern:

```text
one encoder pass
    -> compact dense embedding
    -> fine-grained late-interaction embedding

dense ANN / cheap ranking
    -> small candidate set
late interaction
    -> precise reranking
source-span/page recovery
    -> final context
```

For text retrieval, Motoko should not adopt NeoMME merely because it supports
text. Existing local text encoders/rerankers may remain simpler and more mature.
The transferable point is the representation hierarchy: generate cheap and
expensive retrieval views together when doing so lowers indexing cost and keeps
the two stages semantically aligned.

### 2. Late interaction remains worth tracking beyond images

Motoko's retrieval roadmap already identifies ColBERT-style late interaction as
a possible future improvement over single-vector dense retrieval. NeoMME adds
useful evidence that late interaction can be made substantially more practical
through pooling and quantization rather than treating its raw storage footprint
as fixed.

A future Motoko experiment should therefore evaluate not just:

- dense embedding retrieval versus late interaction;

but also:

- dense-only index;
- uncompressed late-interaction index;
- pooled late-interaction index;
- pooled + quantized late-interaction index;
- dense candidate generation + compressed late-interaction reranking.

The relevant metrics are recall/ranking quality, index bytes, rebuild cost,
query latency, GPU/CPU requirements, and whether provenance/source-span recovery
remains straightforward.

### 3. Visual document retrieval is a deferred evidence lane, not a replacement

NeoMME-Retriever indexes document page screenshots directly. This avoids making
OCR or text extraction the only representation of a PDF page and preserves
visual evidence such as:

- tables and plots;
- diagrams and schematics;
- spatial/layout relationships;
- font size and emphasis;
- labels embedded in figures;
- visually structured forms or reports.

This could eventually matter for Motoko when indexed corpora contain technical
PDFs, scanned documents, slide decks, engineering drawings, financial reports,
or other visually structured sources.

It should **not** become the default retrieval path for ordinary text documents.
Motoko's deterministic text parsing, exact lexical retrieval, structured Org
signals, embeddings, and source-span selection remain cheaper, more inspectable,
and easier to quote precisely when the source is fundamentally textual.

The best eventual architecture is multimodal evidence fusion:

```text
text extraction / deterministic structure
+ lexical retrieval
+ text dense embeddings
+ optional text late interaction
+ optional page-image dense retrieval
+ optional page-image late interaction
+ candidate fusion / reranking
+ recover authoritative text span and/or page image
```

A visual hit should identify a page or region worth inspecting; it should not
silently replace recoverable source text with an opaque image-vector match.

### 4. Preserve multiple representations of the same source

NeoMME is a useful reminder that one source can have several complementary
retrieval representations. A future Motoko PDF/page object could retain links
among:

- original PDF and page number;
- extracted text;
- deterministic layout/metadata where available;
- text chunks/spans;
- page-image fingerprint;
- dense text embedding;
- dense visual embedding;
- optional late-interaction representations.

All representations should resolve back to the same source identity and
provenance. This lets Motoko choose the best lane for a query without creating
parallel, contradictory notions of what the source is.

### 5. Compression should be treated as a first-class index design variable

The 255x reported compression result suggests a broader retrieval-engineering
principle for Motoko: when a representation improves ranking but appears too
large, evaluate structured compression before discarding the technique.

This is relevant to text as well as images. Candidate methods may include:

- vector dimensionality reduction where the encoder supports it;
- scalar/binary quantization;
- token/vector pooling;
- keeping high precision for ephemeral query vectors while storing documents at
  lower precision;
- hot/warm/cold tiers for expensive derived representations;
- rebuilding cold derived vectors from authoritative sources when necessary.

This connects directly to Motoko's existing lifecycle requirement that derived
artifacts remain rebuildable and provenance-linked.

## Why NeoMME should remain deferred for Motoko

A faithful NeoMME integration would currently conflict with several practical
constraints or priorities:

- Motoko is intentionally Python-standard-library-only at runtime, whereas the
  released NeoMME path relies on the Hugging Face / PyTorch ecosystem;
- Motoko's current serving boundary is based on operator-approved local
  llama.cpp routes rather than arbitrary Transformer embedding runtimes;
- image retrieval requires a new ingestion path for PDF rasterization/page
  images, visual-vector storage, model routing, and multimodal context delivery;
- the present retrieval problems are predominantly text, structured document,
  episodic-memory, temporal, and provenance problems;
- visual retrieval adds substantial storage and GPU/indexing complexity even
  with compression.

Therefore NeoMME should be treated as a bibliographic and architectural
reference, not as an implementation task on the current roadmap.

## Conditions for revisiting visual retrieval

Revisit this direction when several of the following become true:

1. Real Motoko usage demonstrates repeated retrieval failures caused by tables,
   plots, diagrams, scanned pages, or layout that text extraction cannot
   preserve.
2. PDF/slide/image corpora become important enough that manual visual inspection
   is a meaningful bottleneck.
3. A local, security-compatible multimodal embedding route can be owned by the
   same reviewed model-routing boundary as other Motoko workers.
4. Visual indexing can remain resumable, checkpointed, realm-local, deletable,
   and rebuildable from authoritative source files.
5. Evals can compare text-only retrieval with visual-only and fused
   text+visual retrieval on Motoko-relevant documents.
6. The measured retrieval gain justifies the additional model, storage, and
   ingestion complexity.

## Suggested future experiment

When visual retrieval becomes justified, start narrowly with a PDF-page side
index rather than redesigning the entire retrieval system.

For a controlled corpus containing tables, diagrams, and ordinary prose,
compare:

1. text hybrid retrieval only;
2. page-image dense retrieval only;
3. page-image late interaction only;
4. text retrieval + page-image dense candidate fusion;
5. text retrieval + image dense candidates + compressed late-interaction
   reranking.

Measure:

- page recall@k and nDCG;
- answer/source correctness;
- performance specifically on tables/figures/layout-dependent questions;
- false positives where visual similarity is not semantically relevant;
- index bytes/page;
- indexing throughput and energy/GPU time;
- query latency;
- final prompt/context size;
- ability to recover an exact source span or visibly relevant region;
- lifecycle behavior after source edit/delete/reindex.

The success criterion should not be "visual retrieval works." It should be that
adding the visual lane fixes a measurable class of failures that Motoko's text
retrieval cannot solve, while keeping source provenance and operational
complexity under control.

## Current recommendation

Keep NeoMME on the retrieval research watchlist, but do not prioritize visual
RAG now.

Borrow immediately at the architectural level:

1. maintain the distinction between cheap dense candidate generation and
   fine-grained late-interaction reranking;
2. evaluate pooling and asymmetric quantization as ways to make high-quality
   fine-grained indexes practical;
3. design future source schemas so multiple retrieval representations can point
   to one authoritative source identity;
4. treat visual page retrieval as an optional evidence lane that can be fused
   with, not substitute for, Motoko's text/structured retrieval.

NeoMME is most valuable to Motoko today as evidence that a future multimodal
retrieval lane can be compact and efficient enough to be realistic when the use
case finally warrants it.

## References

- Lac, A. and Wu, T. (2026). *NeoMME: A Single-Tower Multimodal-Native
  Multilingual Foundation Encoder for Efficient Fine-Tuning and Inference*.
  arXiv:2609.01657:
  <https://arxiv.org/abs/2609.01657>
- H Company / Hugging Face technical article, *NeoMME: an efficient
  Multimodal-native and Multilingual Encoder*:
  <https://huggingface.co/blog/Hcompany/neomme>
- NeoMME Hugging Face collection:
  <https://huggingface.co/collections/Hcompany/neomme>
- NeoMME-260M-Retriever model card:
  <https://huggingface.co/Hcompany/NeoMME-260M-Retriever>
- NeoMME-800M-Retriever model card:
  <https://huggingface.co/Hcompany/NeoMME-800M-Retriever>
- ColPali, visual document retrieval with late interaction:
  <https://arxiv.org/abs/2407.01449>
- ViDoRe benchmark:
  <https://huggingface.co/vidore>

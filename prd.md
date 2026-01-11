# PronounceX TTS (English + Anime Names)

A pronunciation-first **English** neural TTS backend with file-based control over how words are spoken (including **Japanese names / anime terms spoken in English**).

---

## 1) Product Requirements Document (PRD)

### 1.1 Problem

Modern neural TTS can sound great but still:

* mispronounces English edge cases (proper nouns, acronyms, brand names, tech terms)
* butchers Japanese names and anime slang when written in romaji (e.g., “Gojo”, “Sukuna”, “Senpai”, etc.)

Root cause: **G2P guesswork** and inconsistent phoneme inventories.

### 1.2 Goals

1. **High-quality English voice** (modern neural TTS)
2. **Deterministic pronunciation** for:

   * most English words
   * proper nouns and technical terms
   * Japanese names + anime slang **as spoken in English**
3. **File-based** pronunciation control (dictionary packs + overrides)
4. Maintainable: swap models later without rewriting your lexicon

### 1.3 Non-goals

* Speaking native Japanese with pitch accent (this is English speech with Japanese loanwords)
* Voice cloning as the primary focus

### 1.4 Primary Users

* creators (anime / tech narration)
* automation/agent stacks producing spoken output
* accessibility/narration tools

### 1.5 Success Metrics

* **Pronunciation accuracy** on a regression list (target: 98%+ on your curated set)
* **No regressions** when updating dictionaries/models
* Subjective audio quality: “sounds modern / non-robotic”

---

## 2) Locked Technical Approach

### 2.1 Core choice

**Coqui TTS + VITS-style models**, with a pronunciation layer you control.

### 2.2 Why this approach

* VITS models can be trained/packaged with strong phoneme support.
* Coqui provides a well-known model zoo and tooling.

---

## 3) Model Selection (Recommended Coqui Models)

These are model-name strings you can use with the `tts` CLI or Coqui APIs.

### 3.1 Primary “pronunciation-correct” baseline

**`tts_models/en/ljspeech/vits`**

* Description in the model registry: **trained with phonemes**. This makes it the best default for deterministic pronunciation control.

### 3.2 Multi-speaker option (voice variety)

**`tts_models/en/vctk/vits`**

* Multi-speaker VITS model (109 speakers). Useful if you want multiple voices while keeping a similar acoustic backbone.

### 3.3 Alternate English VITS voice option

**`tts_models/en/jenny/jenny`**

* A VITS model trained on the “Jenny (Dioco)” dataset.

**Notes for picking between them**

* If your #1 priority is *pronunciation determinism* → start with **ljspeech/vits**.
* If you want multiple speaker identities without cloning → evaluate **vctk/vits**.
* If you want a different single-voice “feel” → try **jenny/jenny**.

---

## 4) Pronunciation System Design

### 4.1 Canonical representation: IPA

Store pronunciations in **IPA** as your **source of truth**.

* human-auditable
* engine-agnostic
* stable over time

### 4.2 Dictionary layers

Priority order:

1. **Anime/Japanese-in-English dictionary** (Gojo, Sukuna, Senpai, etc.)
2. **English custom dictionary** (names, acronyms, brands, tech terms)
3. **Fallback English G2P** (only for unknown tokens)

### 4.3 What “Japanese-in-English” means

You are *not* generating native Japanese.
You are generating **English speech** where Japanese names are pronounced the way an English-speaking audience expects.

Ruleset targets:

* clear vowels (katakana-like clarity)
* preserve long vowels when important (ō, ū)
* no pitch accent modeling

---

## 5) System Architecture

```
Input Text
  → Tokenizer
  → Pronunciation Resolver (dicts + fallback)
  → IPA → Model-Phoneme Compiler
  → Coqui VITS inference
  → WAV/MP3 output
```

### 5.1 Components

* **Tokenizer**: stable tokenization that preserves casing and punctuation
* **Pronunciation Resolver**: word/phrase matching with priority + optional POS heuristics
* **IPA → phoneme compiler**: converts IPA into the exact phoneme inventory your chosen model expects
* **Synthesizer**: Coqui TTS inference wrapper

---

## 6) Minimal Pronunciation-Override Pipeline (MVP)

### 6.1 Files

```
pronouncex/
  dicts/
    anime_en_ipa.json
    en_custom_ipa.json
    overrides_local.json
  compiled/
    anime_en_phonemes.json
    en_custom_phonemes.json
  src/
    preprocess.py
    ipa_compile.py
    tts_service.py
```

### 6.2 Dictionary format (IPA source of truth)

Example (`dicts/anime_en_ipa.json`):

```json
{
  "Gojo": {"ipa": "ˈɡoʊ.dʒoʊ", "source": "jjk"},
  "Sukuna": {"ipa": "suːˈkuː.na", "source": "jjk"},
  "Senpai": {"ipa": "ˈsɛn.paɪ", "source": "anime"}
}
```

### 6.3 Offline compilation step

* Convert IPA strings into **model phoneme strings** and store into `compiled/*.json`.
* Run:

  * at build time
  * or at service startup

### 6.4 Runtime preprocessing

* Replace matching words/phrases with phoneme blocks.
* Everything else goes through fallback G2P.

---

## 7) IPA vs Custom Phoneme Set (Maintainability Decision)

### Recommendation: **IPA as the canonical store**

**Pros**

* Portable across engines/models
* Human-readable and reviewable
* Future-proof

**Cons**

* Requires a compiler layer (you write/maintain mapping tables)

### When to store engine-native phonemes

Only if you are 100% certain you will never change engines/models.

---

## 8) XTTS vs VITS for Pronunciation Fidelity

### VITS (phoneme-friendly)

* Most deterministic
* Best for strict pronunciation overrides

### XTTS

* Best for voice cloning and multilingual use
* Pronunciation can drift because it optimizes for speaker/style

**Verdict**
For your goal (English pronunciation + anime terms): **VITS first**.

---

## 9) Research + Evaluation Plan

### 9.1 Build a regression list

* 500–2000 items split across:

  * common English words that break TTS
  * your names / brands / acronyms
  * anime names / slang / romaji

### 9.2 Scoring

* Human listening pass/fail per word
* Track diffs by version of:

  * model
  * dictionary pack
  * IPA compiler

### 9.3 Iteration loop

1. Add/adjust IPA entry
2. Recompile
3. Re-run regression set
4. Lock in the change

---

## 10) Implementation Checklist

### MVP (1–2 days)

* [ ] Choose initial model: `tts_models/en/ljspeech/vits`
* [ ] Implement dictionary resolver + phrase matching
* [ ] Implement IPA → phoneme compiler (small supported subset first)
* [ ] Build a minimal `tts_service.py` that returns WAV

### V1 (1–2 weeks)

* [ ] Expand IPA mapping coverage for English
* [ ] Add phrase-level dictionary entries (multi-token)
* [ ] Add packaging/versioning for dictionary bundles
* [ ] Add regression suite + CI checks

---

## 11) References (Model registry evidence)

* Model registry includes:

  * `tts_models/en/ljspeech/vits` description: trained with phonemes
  * `tts_models/en/vctk/vits` description: VCTK 109 speakers
  * `tts_models/en/jenny/jenny` description: Jenny(Dioco) dataset

---

# 12) API Service for Ebook → Audio (Ultra-Think Design)

This section specifies a production-grade HTTP API that an ebook reader can call to convert text into audio while preserving pronunciation, pacing, and chapter/paragraph structure.

## 12.1 Design Principles

* **Deterministic audio**: same input + same dictionaries + same model ⇒ same output.
* **Chunking-aware prosody**: chunk boundaries must not sound like hard stops.
* **Streaming-first**: support low-latency playback while synthesis continues.
* **Cache everything**: repeated passages should be near-instant.
* **Pronunciation is a first-class dependency**: dictionary versions are part of cache keys.

## 12.2 Core Concepts

### 12.2.1 Book + Voice + Dictionary = Render Context

A render context defines exactly how audio is produced.

* `model_id` (Coqui model name or internal alias)
* `voice_id` (speaker selection if multi-speaker)
* `sample_rate`
* `dict_pack_ids` + versions
* `reading_profile` (speed, pause rules, emphasis, etc.)

### 12.2.2 Input Units

Ebook content is structured; keep that structure:

* **chapter** → paragraphs → sentences
* Each unit gets a stable ID (for caching and resume).

### 12.2.3 Output Units

Return audio in two layers:

* **segment**: audio for a chunk of text (typically 1–3 sentences)
* **manifest**: an ordered list of segments with timing/metadata

## 12.3 Chunking Strategy (Critical)

### Goals

* Avoid GPU/CPU spikes from huge text blocks.
* Maintain natural flow across segments.
* Make seeking and caching easy.

### Recommended Chunking

* Split by paragraph first.
* Within paragraph, split into chunks of ~**160–300 characters** or **1–3 sentences**.
* Apply “soft join” to avoid robotic resets:

  * carry-over punctuation context
  * add micro-pauses at boundaries (configurable)
  * avoid splitting inside quotes or parentheses when possible

### Boundary Smoothing

When chunking, apply these rules:

* If a chunk ends without terminal punctuation, add a small pause at playback join (not inside audio).
* If a chunk ends with comma/semicolon, use shorter pause.
* If a chunk ends with period/exclamation/question, use longer pause.

This yields natural pacing without requiring the model to synthesize cross-chunk context.

## 12.4 Pronunciation Pipeline in the API

Runtime steps per chunk:

1. Normalize text (unicode NFKC, smart quotes, ellipses, em-dashes)
2. Apply phrase-level dictionary matches first (longest match wins)
3. Apply word-level dictionary matches
4. Convert matched IPA → model-phonemes via compiler
5. Inject phoneme blocks into text (engine-specific syntax)
6. Send processed text to Coqui inference

### Dictionary Matching Rules

* Priority: `anime > english > local overrides`
* Prefer **case-preserving** match with a case-insensitive fallback.
* Support aliases: e.g., `"Gojou"` → `"Gojo"`.

### Versioned Dictionary Packs

All dictionaries are versioned and shipped as packs:

* `anime_en:v1.0.0`
* `en_core:v1.2.3`
* `local_overrides:v0.0.1`

Dictionary versions must be included in:

* request metadata
* cache key
* response manifest

## 12.5 API Surface (Minimal + Production-Ready)

### 12.5.1 Health

* `GET /health` → OK

### 12.5.2 Voices / Models

* `GET /v1/models`
* `GET /v1/voices` (if multi-speaker)

### 12.5.3 Dictionary Packs

* `GET /v1/dicts` → available packs
* `POST /v1/dicts/upload` → upload a local override pack
* `POST /v1/dicts/compile` → compile IPA → phonemes for the active model

### 12.5.4 Synthesis (Two Modes)

#### A) Streaming (recommended for ebook playback)

* `POST /v1/tts/stream`

  * Request: text + context (model/voice/dicts/reading_profile)
  * Response: chunked HTTP audio stream (WAV or OGG Opus)
  * Server emits headers with a `job_id`

#### B) Job-based (recommended for chapter download/offline)

* `POST /v1/tts/jobs` → returns `job_id`
* `GET /v1/tts/jobs/{job_id}` → status + manifest
* `GET /v1/tts/jobs/{job_id}/segments/{segment_id}` → audio bytes

## 12.6 Audio Formats

### Default

* **OGG Opus** for streaming and size efficiency.

### Optional

* WAV for debugging
* MP3 only if a client requires it

## 12.7 Caching & Idempotency

### Cache Key

Cache audio per segment using a stable key:

* normalized text
* model_id + voice_id
* dict pack IDs + versions
* reading_profile (speed/pitch)
* compiler version

Example key hash:
`sha256(text_norm + model + voice + dicts + profile + compiler_ver)`

### Cache Layers

* In-memory LRU (hot segments)
* Disk cache (persist across restarts)
* Optional: S3-compatible object store for distributed setups

### Idempotency

Requests accept an optional `Idempotency-Key` header.
If repeated, server returns the same `job_id`.

## 12.8 Concurrency & Performance

### Baseline

* CPU inference may be sufficient for single-user ebook playback.
* GPU strongly recommended for multi-user or high throughput.

### Worker Model

* API process handles HTTP + orchestration.
* Worker pool handles inference.
* Queue: Redis (RQ/Celery) or built-in asyncio queue for single node.

### Backpressure

* Streaming endpoints must apply per-client rate control.
* Jobs have concurrency limits per tenant.

## 12.9 Reading Profiles (Ebook-Specific)

A reading profile controls pacing and clarity:

* `rate`: 0.8–1.2
* `pause_scale`: 0.8–1.3
* `quote_mode`: reduces pause jitter inside dialogue
* `acronym_mode`: spells out acronyms (optional)
* `number_mode`: read years vs cardinal numbers

Profiles are part of the cache key.

## 12.10 Observability

* Structured logs with request_id/job_id
* Metrics: synth time, realtime factor (RTF), cache hit rate
* Tracing around: preprocess → compile → inference → encode → stream

## 12.11 Security

* API key per client app
* Rate limits
* Upload validation for dictionary packs

## 12.12 Roadmap

### MVP

* Job-based synthesis for paragraphs
* Dictionary packs + overrides
* Disk cache

### V1

* Streaming endpoint
* Chapter manifests + seeking
* Regression pronunciation tests

### V2

* Multi-voice support (VCTK)
* User-specific override packs
* Optional distributed cache

# Technical Design Document: Same Model, Two Inference Services

**Project:** Inference benchmark of `gpt-oss-120b` on Cerebras vs. Together AI
**Author:** Sam Mirazi
**Status:** Approved plan, ready for pilot
**Target publish date:** Before Thursday, October 29, 2026
**Publication:** Advisee AI on Substack (https://advisee.substack.com/)

---

## 1. Instructions for the AI coding assistant (read first)

You are helping implement this project inside Cursor on Windows 11. Before writing or changing any code:

1. Read this entire document.
2. Read the existing file `pilot_benchmark.py`. It is the starting point. Keep its structure unless a change is needed to meet this document.
3. Do not invent API behavior. Any field name, parameter, or token count that is not confirmed by a real API response must be treated as **unknown** until the pilot run confirms it.
4. Never hardcode API keys. Read them from environment variables only.
5. Do not use OpenRouter or any other routing layer. Both services are called directly.
6. Work in phases (Section 12). Finish and verify the pilot before building the full benchmark.
7. After each run, show the console summary and point out anything unexpected (missing fields, errors, truncations, cache hits).
8. Keep the code simple and readable. This is for a short public article, not a production system.

---

## 2. Purpose

Produce one short, credible, reproducible benchmark and a Substack article (about 1,000 to 1,500 words) that answers:

> **How does the same AI model perform on two different inference services: Cerebras vs. a GPU-based provider (Together AI)?**

The article must demonstrate:
- Hands-on benchmarking with documented methodology
- Fair comparison design
- Honest reporting of limitations
- Clear technical writing

Secondary purpose: a portfolio piece for the Cerebras Hardware Research Analyst interview.

---

## 3. Scope

### In scope
- One model: `gpt-oss-120b`
- Two services, each called directly through its own OpenAI-compatible API:
  - **Cerebras Inference API** (model ID `gpt-oss-120b`)
  - **Together AI** (model ID `openai/gpt-oss-120b`)
- Two workloads:
  - **Test A, short prompt:** about 100 input tokens, short answer
  - **Test B, long prompt:** about 5,000 input tokens, a Q&A task over a document
- 20 paired runs per test (80 requests total in the full benchmark)
- Streaming responses with chunk-level timing
- Answer quality scoring against a checklist written before testing
- Summary statistics, two charts, raw data export

### Out of scope (do not build)
- Any routing layer (OpenRouter, LiteLLM proxy, etc.)
- Local GPU testing
- Agent or multi-step demo
- Concurrency or load testing (requests are sent one at a time)
- Other models or other providers
- Any claim that hardware architecture *causes* the results

### Framing rule
This benchmark compares **services**, not chips. Measured times include network latency, queuing, and serving software. The article must say so.

---

## 4. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Home |
| Editor | Cursor (Claude Code CLI in Cursor's integrated terminal) |
| Shell | PowerShell |
| Language | Python 3.10 or newer |
| Required packages | `openai`, `pandas`, `matplotlib` |
| Optional package | `python-dotenv` (to load keys from a `.env` file) |

### Setup commands (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install openai pandas matplotlib python-dotenv
```

### API keys
Store keys in a `.env` file in the project root (never commit it):
```
CEREBRAS_API_KEY=your_cerebras_key
TOGETHER_API_KEY=your_together_key
```
Add `.env`, `.venv/`, and `__pycache__/` to `.gitignore`.

---

## 5. Services

| Service | Base URL | Model ID | Key env var |
|---|---|---|---|
| Cerebras | `https://api.cerebras.ai/v1` | `gpt-oss-120b` | `CEREBRAS_API_KEY` |
| Together AI | `https://api.together.xyz/v1` | `openai/gpt-oss-120b` | `TOGETHER_API_KEY` |

Both are OpenAI Chat Completions compatible, so use the `openai` Python SDK with a custom `base_url` for each.

**Verify in the pilot:** both model IDs are accepted, and both services return streamed output.

---

## 6. Matched settings

All requests on both services use identical settings:

| Setting | Value | Note |
|---|---|---|
| `temperature` | `1.0` | Same on both |
| `max_tokens` | `2048` | Same on both. If the pilot shows truncation (`finish_reason == "length"`), raise it equally on both |
| `reasoning_effort` | `"medium"` | **Verify** both services accept it. If one rejects it, report this and stop; do not silently drop the parameter on one side only |
| `stream` | `True` | Required for timing |
| `stream_options` | `{"include_usage": True}` | Required for token counts. **Verify** both services return a usage object |

Prompts are word-for-word identical on both services.

---

## 7. Run design

### Pairing and ordering
- Each **pair** = one Cerebras request + one Together request with the **same run ID**.
- Alternate which service goes first in each pair (even pairs: Cerebras first; odd pairs: Together first) to reduce time-of-day and warm-up effects.
- Requests are sequential (never concurrent).
- Optional: a short pause (for example 2 seconds) between requests to avoid rate limits. Use the same pause for both services.

### Run ID and caching
- Generate a short unique run ID per pair (for example 8 hex characters).
- Put it at the **start** of the prompt: `[run 3fa9c21b]\n<prompt>`. A unique prefix reduces prefix-cache reuse across pairs.
- This does **not** guarantee caching is disabled. Record any cache usage the API reports (for example `usage.prompt_tokens_details.cached_tokens`). If a service reports nothing about caching, record cache behavior as **unknown** and disclose it in the article.

### Warm-up
- Send one warm-up request per service before the measured runs. Store it but exclude it from statistics (flag `is_warmup: true`).

---

## 8. Prompts and quality checklists

Prompts and their checklists must be written and saved **before** any measured run. Store them in `prompts/`.

### Test A, short prompt (`prompts/short.txt`)
Example (the pilot already uses this):
> In two or three sentences, explain why the boiling point of water is lower at high altitude than at sea level.

Checklist (`prompts/short_checklist.json`), each item worth 1 point:
1. Mentions lower atmospheric (air) pressure at altitude
2. States that water boils when its vapor pressure equals surrounding pressure (or equivalent)
3. Concludes that less heat / lower temperature is needed to boil
4. Stays within two or three sentences

### Test B, long prompt (`prompts/long.txt`)
- Use a **public-domain** document of about 4,500 to 5,000 tokens (for example, a section of a U.S. government report or a Project Gutenberg text). Do not use copyrighted articles.
- Append 3 specific questions whose answers are clearly stated in the document.
- Save the source and its license/public-domain status in `prompts/long_source.md`.

Checklist (`prompts/long_checklist.json`): one item per expected fact (for example 3 to 5 items).

### Scoring
- Write a simple scorer (`score.py`) that checks each response against the checklist using keyword/phrase matching, and outputs a score per response.
- Sam will manually review a sample of responses to confirm the automatic scores are reasonable. Flag any response where the automatic score is uncertain.
- Also record per response: truncated (yes/no), error (yes/no and message), empty answer (yes/no).

---

## 9. Metric definitions

All times are measured on the client with `time.perf_counter()`, starting immediately before the API call.

The streaming response arrives in **chunks**. A chunk can contain more than one token, so the script measures **chunks with text**, not individual tokens. The article must say "first text chunk," not "first token."

| Metric | Definition |
|---|---|
| **Time to first reasoning chunk** | Request start until the first chunk containing non-empty reasoning text |
| **Time to first answer chunk** | Request start until the first chunk containing non-empty visible answer text (`delta.content`) |
| **Reasoning window** | Time of first reasoning chunk to time of last reasoning chunk |
| **Answer window** | Time of first answer chunk to time of last answer chunk |
| **Reasoning speed** | Reasoning tokens ÷ reasoning window |
| **Answer speed** | Answer tokens ÷ answer window |
| **Total response time** | Request start until the stream ends |
| **Cost per run** | (input tokens × input price) + (output tokens × output price), from each provider's published prices on the test date |

### Token counts
- Use the token counts **reported by each API** in the usage object. Do not estimate tokens by counting characters.
- Reasoning tokens: expected at `usage.completion_tokens_details.reasoning_tokens`. **Verify in the pilot.**
- Answer tokens = completion tokens minus reasoning tokens (only if both are reported).
- If a service does not report a value needed for a metric, mark that metric **"unavailable"** for that service. Never fill it in with a guess, and never compare a measured value against an estimated one.

### Reasoning text field
- The reasoning text may arrive in `delta.reasoning`, `delta.reasoning_content`, or another field. The pilot logs every non-empty delta key so we can confirm. Update `REASONING_KEYS` in the code only based on what the pilot actually shows.

### Matching rule
Every metric must use the **same definition on both services**. If a definition can only be measured on one service, report it as unavailable for the other and do not include it in a head-to-head comparison.

---

## 10. Statistics and reporting

- **Headline number:** median for each metric, per service, per test.
- **Show all runs:** a strip or dot plot of every individual run, so readers see the spread.
- **p95:** report as exploratory only. With 20 runs it depends heavily on the slowest one or two requests. Label it clearly.
- Report counts of errors, truncations, and empty answers per service.
- Report quality scores (mean and count of perfect scores) per service, per test.
- Never drop a failed run silently. Exclude it from timing statistics, but count and report it.

### Charts (`charts/`)
1. **Time to first answer chunk**, Test A and Test B, both services, every run shown as a dot with the median marked.
2. **Answer speed (tokens per second)**, same layout.

Chart rules: clear titles, labeled axes with units, the same service color in every chart, readable in both light and dark backgrounds, exported as PNG at a size suitable for Substack (about 1200 px wide).

---

## 11. Project structure

```
inference-benchmark/
├── .env                      # API keys (not committed)
├── .gitignore
├── README.md                 # what this is, how to reproduce
├── TDD_Inference_Benchmark.md
├── pilot_benchmark.py        # Phase 1: pilot (existing file)
├── benchmark.py              # Phase 2: full benchmark
├── score.py                  # quality scoring against checklists
├── analyze.py                # statistics, summary table, charts
├── estimate_cost.py          # budget estimate before running
├── prompts/
│   ├── short.txt
│   ├── short_checklist.json
│   ├── long.txt
│   ├── long_checklist.json
│   └── long_source.md
├── results/
│   ├── pilot_results.jsonl
│   ├── pilot_chunks.jsonl
│   ├── benchmark_results.jsonl
│   └── summary.csv
└── charts/
    ├── time_to_first_answer.png
    └── answer_speed.png
```

---

## 12. Implementation phases

### Phase 0: Setup
- Create the folder structure, virtual environment, `.env`, `.gitignore`.
- **Done when:** `python -c "import openai, pandas, matplotlib"` runs without errors and both keys load from `.env`.

### Phase 1: Pilot (`pilot_benchmark.py`, already written)
Run 3 pairs of the short prompt. The pilot must answer these questions, and the assistant must report the answers explicitly:

1. Do both services accept the model ID, `temperature`, `max_tokens`, `reasoning_effort`, and `stream_options`?
2. Which delta field carries reasoning text on each service?
3. Does each service return a usage object at the end of the stream?
4. Does each usage object include `completion_tokens_details.reasoning_tokens`?
5. Does each usage object report cached prompt tokens?
6. Did any response truncate or error?
7. Which metrics in Section 9 are measurable on both services, and which are unavailable?

Changes allowed in Phase 1: update `REASONING_KEYS`, field paths for token counts and cache usage, and settings that one service rejects (only by reporting the problem, not by silently changing one side). Add `.env` loading with `python-dotenv`. Move outputs into `results/`.

- **Done when:** all 6 pilot requests succeed and the 7 questions above are answered in writing.

### Phase 2: Budget estimate (`estimate_cost.py`)
- Inputs: number of requests, approximate input and output tokens per test (from pilot usage data), each provider's current published price per million tokens (Sam enters these manually, with the date checked).
- Output: estimated cost per service and total.
- **Done when:** Sam confirms the estimate fits the budget before Phase 3 runs.

### Phase 3: Full benchmark (`benchmark.py`)
- Reuse the pilot's request and timing logic (refactor into shared functions if helpful).
- Load prompts from `prompts/`.
- 1 warm-up request per service, then 20 pairs for Test A and 20 pairs for Test B.
- Alternate service order within pairs. Same run ID within a pair.
- Write one JSON line per request to `results/benchmark_results.jsonl` immediately after each request (so a crash does not lose earlier data).
- Retry policy: none. A failed request is recorded as failed and the run continues.
- **Done when:** 80 measured requests are recorded (successful or failed), plus warm-ups.

### Phase 4: Scoring (`score.py`)
- Score every response against its checklist.
- Add `quality_score`, `quality_max`, and `checklist_hits` to each record (write to a new file or a scored copy; never overwrite raw results).
- **Done when:** every successful response has a score, and Sam has spot-checked at least 5 responses per service.

### Phase 5: Analysis (`analyze.py`)
- Compute medians, p95 (exploratory), error/truncation counts, and quality scores per service per test.
- Write `results/summary.csv` and print a markdown table ready to paste into the article.
- Generate the two charts in Section 10.
- **Done when:** summary table and both charts exist and the numbers match the raw data.

### Phase 6: Publish
- Push the repo to GitHub (public) with README.
- Write and publish the Substack article (Section 14).

---

## 13. Data schema (one JSON line per request)

```json
{
  "timestamp_utc": "2026-10-25T18:03:11.123Z",
  "phase": "pilot | benchmark",
  "test": "short | long",
  "service": "cerebras | together",
  "model": "gpt-oss-120b",
  "run_id": "3fa9c21b",
  "pair_index": 4,
  "order_in_pair": 1,
  "is_warmup": false,
  "settings": {"temperature": 1.0, "max_tokens": 2048, "reasoning_effort": "medium"},
  "error": null,
  "finish_reason": "stop",
  "truncated": false,
  "delta_keys_seen": ["content", "reasoning"],
  "first_reasoning_chunk_s": 0.21,
  "first_answer_chunk_s": 0.48,
  "reasoning_window_s": 0.25,
  "answer_window_s": 0.09,
  "total_s": 0.61,
  "prompt_tokens": 112,
  "completion_tokens": 310,
  "reasoning_tokens": 240,
  "answer_tokens": 70,
  "reasoning_tok_per_s": 960.0,
  "answer_tok_per_s": 777.8,
  "cached_prompt_tokens": null,
  "cache_status": "reported | unknown",
  "usage_raw": {},
  "answer_text": "...",
  "quality_score": null,
  "quality_max": null
}
```

Any value that a service does not provide is `null` and displayed as "unavailable."

---

## 14. Article outline (for Sam, not for code)

1. **The question:** same model, two services; why inference speed matters to developers
2. **Setup and methodology:** services, settings, prompts, pairing, metric definitions in plain language
3. **Results:** one summary table and two charts
4. **Context:** brief background on how the two architectures differ, clearly labeled as background, not as the proven cause
5. **Limitations:** two workloads, one model, one location, services not chips, small sample, caching uncertainty, single test date
6. **Takeaway for developers**
7. **Reproduce it:** link to the GitHub repo

Principle: the results decide the story, even if Cerebras does not win every metric.

---

## 15. Error handling and safety

- Catch exceptions per request, record the error message, and continue.
- Do not retry automatically (retries would distort timing comparisons).
- Stop the whole run only if a key is missing or a service rejects the model or a required setting in the pilot.
- Respect rate limits: if errors indicate rate limiting, stop and report rather than hammering the API.
- Never print or log API keys.
- Do not publish raw responses that contain anything other than the model's answers to our own prompts.

---

## 16. Acceptance criteria (project complete)

- [ ] Pilot ran successfully and all 7 pilot questions are answered in writing
- [ ] Every metric is either measured identically on both services or marked unavailable
- [ ] Cost estimate approved before the full run
- [ ] 80 measured requests recorded, with failures counted
- [ ] Quality scores recorded and spot-checked
- [ ] Summary table and two charts generated from raw data
- [ ] Repo on GitHub with README, code, prompts, checklists, raw results, charts
- [ ] Article published with methodology and limitations sections

---

## 17. Timeline

| Day | Work |
|---|---|
| Day 1 | Phase 0, Phase 1 (pilot), write prompts and checklists |
| Day 2 | Phase 2 (cost estimate), Phase 3 (full run), Phase 4 (scoring), Phase 5 (analysis) |
| Day 3 | Phase 6: GitHub repo and article published |

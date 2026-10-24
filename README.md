# Same Model, Two Inference Services: Cerebras vs. Together AI

A small, reproducible benchmark of `gpt-oss-120b` served by two providers, each called directly through its own OpenAI-compatible API:

- **Cerebras Inference API** (`gpt-oss-120b`)
- **Together AI** (`openai/gpt-oss-120b`)

This compares **services**, not chips. All times are measured on the client and include network latency, queueing, and serving software.

Article: [Advisee AI on Substack](https://advisee.substack.com/)

## Results (October 24, 2026, re-run)

> **Note: these results replace the first run.** In the first run, the OpenAI SDK's default `max_retries=2` silently retried requests that Cerebras rejected with HTTP 429. The first run used the Cerebras free tier (5 requests per minute, lower priority); this v2 run used Pay as You Go (1,000 requests per minute). In the first run, the SDK waited out each 429's `retry-after` (52–58 s) and retried, which produced the 50–58 second delays first reported for 5 Cerebras requests. `retry_check.py` reproduced this (429s with `retry-after` 52–58 s once the per-minute limit was used up). The first run's files are kept unchanged: `results/benchmark_results.jsonl`, `results/benchmark_scored.jsonl`, `results/spot_check.md`, and `results/manual_review.json`.

20 measured runs per service per test. Medians, with ranges in brackets.

| Test | Service | First answer chunk (s) [min–max] | Output speed (tok/s) [5th–95th percentile] | Errors (429s) | Correct answers |
|---|---|---|---|---|---|
| A: short prompt (~100 tokens) | Cerebras | 0.24 [0.20–0.38] | 1,834 [1,133–3,344†] | 0 (0) | 20/20 |
| A: short prompt (~100 tokens) | Together AI | 0.61 [0.35–1.32] | 198 [127–233] | 0 (0) | 19/20\* |
| B: long prompt (~4,460 tokens) | Cerebras | 0.39 [0.35–0.57] | 2,279 [1,172–2,579] | 0 (0) | 20/20 |
| B: long prompt (~4,460 tokens) | Together AI | 1.51 [1.13–2.53] | 186 [90–234] | 0 (0) | 20/20 |

\*Both services ran the same model at temperature 1.0. The one incomplete Together answer reflects normal sampling variation, not a service quality difference.

†Above Cerebras's advertised ~3,000 tok/s for this model: the same large-chunk timing artifact on short streams described below.

All 84 requests (80 measured plus 4 warm-ups) returned HTTP 200, with no 429s, errors, truncations, or empty answers. The slowest Cerebras request finished in 0.60 s; the slowest Together request in 3.66 s.

Output speed is shown as 5th to 95th percentile. Cerebras's fastest short runs (up to 8,739 tok/s, above its advertised ~3,000 tok/s for this model) are a timing artifact of short streams arriving as a few large chunks, for example 92 tokens within 11 ms. Full min–max values are in `results/summary.csv`.

![Time to first answer chunk](charts/time_to_first_answer.png)

![Output speed](charts/output_speed.png)

![Answer quality](charts/quality_score.png)

### Notable findings

- **Silent SDK retries can masquerade as latency.** The first run's 50–58 second Cerebras "delays" were rate-limit rejections (HTTP 429) that the OpenAI SDK retried automatically after waiting out `retry-after`. Nothing in the response showed it. Benchmarks that use the SDK defaults can report a rate limit as a slow request; this re-run sets `max_retries=0` and logs every status code.
- **Reaction to the run ID.** Each prompt starts with a unique `[run <id>]` prefix to reduce prefix-cache reuse. In the first run, 3 of 20 Together short-prompt answers treated it as a command ("I can't run that command") and omitted the vapor-pressure explanation. In the re-run, no answer from either service did this, so it is an occasional prompt-format artifact, not a consistent quality difference.
- **Caching.** Cerebras reported 0 cached prompt tokens. Together reported 66–69 cached tokens on every request, consistent with the fixed chat-template text that comes before the unique run ID.

## Method

| Setting | Value (identical on both services) |
|---|---|
| `temperature` | 1.0 |
| `max_tokens` | 2048 |
| `reasoning_effort` | `medium` |
| Streaming | on, with `stream_options={"include_usage": True}` |

- **Pairs.** Each pair is one Cerebras and one Together request with the same run ID and identical prompt. Service order alternates between pairs, short and long pairs alternate, and requests run one at a time with a 2-second pause after every request, the same for both services.
- **No retries.** Both clients use `max_retries=0`. Every request logs its HTTP status code and rate-limit headers; a 429 is recorded as a failed request and never retried. The 2-second pause keeps Cerebras at no more than about 15 requests per minute, well under the account's confirmed limit of 1,000 requests per minute (Pay as You Go).
- **Warm-up.** One request per service per test, stored but excluded from statistics.
- **Token counts.** As reported by each API's usage object, never estimated.
- **Time to first answer chunk.** Request start until the first chunk with visible answer text. Chunks can hold several tokens, so this is "first text chunk," not "first token."
- **Output speed.** Completion tokens ÷ (total response time − time to first reasoning chunk). It uses the whole stream, so chunk size distorts it far less (see the short-stream note under Results). Per-phase reasoning and answer speeds are in the raw data as exploratory only: Cerebras sends 9–50 large chunks per response (Together: 68–296), so its per-phase windows are too short to be reliable.
- **Quality.** Each answer is scored against a checklist written before testing (`prompts/*_checklist.json`) by keyword matching (`score.py`), then spot-checked by hand (`results/manual_review_v2.json`).
- **p95** values in `results/summary.csv` are exploratory; with 20 runs they depend on the slowest one or two requests.

### Prompts

- **Test A:** "In two or three sentences, explain why the boiling point of water is lower at high altitude than at sea level."
- **Test B:** an excerpt of about 3,600 words from the *Report of the Presidential Commission on the Space Shuttle Challenger Accident* (1986), Chapter IV, followed by 3 factual questions. Public domain; see `prompts/long_source.md`.

## Limitations

- Two workloads, one model, one client location, one test date.
- Measures services, not chips: network, queueing, and serving software are all included.
- 20 runs per service per test is a small sample.
- Prompt caching cannot be fully controlled; it is recorded as each API reports it.
- Requests are sequential; no concurrency or load testing.
- Prices are each provider's published rates on the test date.
- Cerebras ran on a Pay as You Go account (1,000 requests per minute); results on lower tiers can differ.

## Reproduce

Requires Python 3.10 or newer and API keys for both services.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install openai pandas matplotlib python-dotenv
```

Create `.env` in the project root:

```
CEREBRAS_API_KEY=your_cerebras_key
TOGETHER_API_KEY=your_together_key
```

Then run each phase:

```powershell
python pilot_benchmark.py   # 3 short pairs + 1 long pair, checks API fields
python estimate_cost.py     # budget estimate from pilot token counts
python benchmark.py         # 4 warm-ups + 80 measured requests (move results/benchmark_results_v2.jsonl aside first)
python score.py             # scored copy + spot-check sheet
python analyze.py           # summary.csv, markdown table, charts
```

The full benchmark cost about $0.06 at the prices in `estimate_cost.py`.

## Files

| Path | Contents |
|---|---|
| `pilot_benchmark.py` | Pilot run and the shared request and timing code |
| `estimate_cost.py` | Budget estimate and per-million-token prices |
| `benchmark.py` | Full benchmark |
| `retry_check.py` | 10 Cerebras-only requests with retries off, logging status codes and rate-limit headers |
| `score.py` | Checklist scoring |
| `analyze.py` | Statistics, summary table, charts |
| `prompts/` | Prompts, checklists, long-prompt source |
| `results/` | Raw results, scored copy, manual review, summary |
| `charts/` | Chart PNGs |
| `TDD_Inference_Benchmark.md` | Technical design document |

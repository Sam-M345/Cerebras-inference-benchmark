# Todo

## Phase 0: Setup
- [x] Create `.venv` and install `openai`, `pandas`, `matplotlib`, `python-dotenv`
- [x] Create `.gitignore`, `.env`, `prompts/`, `results/`, `charts/`
- [x] Sam: paste API keys into `.env`

## Prompts
- [x] `prompts/short.txt` and `prompts/short_checklist.json`
- [x] `prompts/long.txt` (Challenger report, Chapter IV excerpt) and `prompts/long_checklist.json`
- [x] `prompts/long_source.md`

## Phase 1: Pilot
- [x] Load keys from `.env`
- [x] Load prompts from `prompts/`
- [x] 3 short pairs + 1 long pair
- [x] Save first and last raw chunks
- [x] Store `prompt_tokens`
- [x] Write outputs to `results/`
- [x] Run `python pilot_benchmark.py` (8/8 succeeded)
- [x] Answer the 7 pilot questions in writing
- [x] Sam: decide the speed metric (output speed is headline; per-phase speeds exploratory)

## Phase 2: Cost estimate
- [x] `estimate_cost.py` (prices checked 2026-10-24): about $0.06 total
- [x] Sam: approve budget

## Phase 3: Full benchmark
- [x] `benchmark.py`: 80 measured + 4 warm-ups, 0 errors, 0 truncations
- [x] Sam: decide how to report 5 Cerebras requests that waited 50-58 s before the first chunk (TDD Section 10)

## Phase 4: Scoring
- [x] `score.py`: scored copy + `results/spot_check.md`
- [x] Sam: spot-check responses (verdicts in `results/manual_review.json`)
- [x] Report: Together had 3 substantive short-task misses (reacted to run ID) + 1 scorer false negative; no rerun
- [x] Sam: verdict for 5th Together sample (long pair 17, run 91ccd1b8): correct
- [x] Phase 4 complete

## Phase 5: Analysis
- [x] `analyze.py`: `results/summary.csv`, markdown table, three charts

## Decisions
- Warm-up: one per service per test (Phase 3)
- Full benchmark: alternate short and long pairs (Phase 3)
- Missing reasoning token counts: mark reasoning speed "unavailable"

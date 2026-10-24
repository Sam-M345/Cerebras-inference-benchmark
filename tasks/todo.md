# Todo

## Phase 0: Setup
- [x] Create `.venv` and install `openai`, `pandas`, `matplotlib`, `python-dotenv`
- [x] Create `.gitignore`, `.env`, `prompts/`, `results/`, `charts/`
- [ ] Sam: paste API keys into `.env`

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
- [ ] Sam: run `python pilot_benchmark.py`
- [ ] Answer the 7 pilot questions in writing

## Decisions
- Warm-up: one per service per test (Phase 3)
- Full benchmark: alternate short and long pairs (Phase 3)
- Missing reasoning token counts: mark reasoning speed "unavailable"

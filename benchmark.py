r"""
Full benchmark (Phase 3): gpt-oss-120b on Cerebras vs. Together AI.

Reuses the pilot's request and timing logic. For each test, one warm-up
request per service, then 20 measured pairs per test. Short and long pairs
alternate, service order alternates within each test, requests are sequential.
Each record is written to results/benchmark_results.jsonl as soon as it finishes.

Usage (Windows PowerShell):
  .\.venv\Scripts\Activate.ps1
  python benchmark.py
"""

import json
import time
import uuid
from statistics import median

from dotenv import load_dotenv

from pilot_benchmark import RESULTS_DIR, SERVICES, fmt, load_prompt, make_client, run_request

TESTS = ("short", "long")
PAIRS_PER_TEST = 20
PAUSE_S = 2  # same pause after every request, both services
OUTPUT_FILE = RESULTS_DIR / "benchmark_results.jsonl"


def service_order(pair_index):
    return ["cerebras", "together"] if pair_index % 2 == 0 else ["together", "cerebras"]


def main():
    load_dotenv()
    if OUTPUT_FILE.exists():
        raise SystemExit(f"{OUTPUT_FILE} already exists. Move or rename it first; raw results are never overwritten.")

    clients = {s: make_client(s) for s in SERVICES}
    prompts = {test: load_prompt(test) for test in TESTS}

    schedule = []  # (test, pair_index, is_warmup)
    for test in TESTS:
        schedule.append((test, 0, True))
    for pair_index in range(PAIRS_PER_TEST):
        for test in TESTS:
            schedule.append((test, pair_index, False))

    RESULTS_DIR.mkdir(exist_ok=True)
    results = []
    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for test, pair_index, is_warmup in schedule:
            run_id = uuid.uuid4().hex[:8]
            label = "warm-up" if is_warmup else f"pair {pair_index + 1}/{PAIRS_PER_TEST}"
            for order_in_pair, service in enumerate(service_order(pair_index), start=1):
                print(f"{test} {label} | {service} | run {run_id} ...", flush=True)
                record = run_request(clients[service], service, test, prompts[test], run_id)
                record.pop("raw_chunks", None)
                record.update(
                    {
                        "phase": "benchmark",
                        "pair_index": pair_index,
                        "order_in_pair": order_in_pair,
                        "is_warmup": is_warmup,
                        "cache_status": "unknown" if record.get("cached_prompt_tokens") is None else "reported",
                        "empty_answer": not record["error"] and not record.get("answer_text"),
                    }
                )
                output.write(json.dumps(record, default=str) + "\n")
                output.flush()
                results.append(record)

                if record["error"] and record["error"].startswith("RateLimitError"):
                    raise SystemExit(f"Rate limited by {service}; stopping. Error: {record['error']}")
                time.sleep(PAUSE_S)

    print_summary(results)


def print_summary(results):
    measured = [r for r in results if not r["is_warmup"]]
    print(f"\n================ BENCHMARK SUMMARY ({len(measured)} measured requests) ================")
    for test in TESTS:
        for service in SERVICES:
            runs = [r for r in measured if r["test"] == test and r["service"] == service]
            ok = [r for r in runs if not r["error"]]

            def median_of(key):
                values = [r[key] for r in ok if r.get(key) is not None]
                return median(values) if values else None

            print(
                f"{test:<6} {service:<9} | runs {len(runs)} | errors {len(runs) - len(ok)} | "
                f"truncated {sum(r['truncated'] for r in ok)} | empty {sum(r['empty_answer'] for r in ok)} | "
                f"median first answer chunk {fmt(median_of('first_answer_chunk_s'))}s | "
                f"median output tok/s {fmt(median_of('output_tok_per_s'), 1)} | "
                f"median cached prompt tokens {fmt(median_of('cached_prompt_tokens'))}"
            )
    print(f"\nFull details: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

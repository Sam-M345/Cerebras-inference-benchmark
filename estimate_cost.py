"""
Budget estimate for the full benchmark (Phase 2).

Token counts per request come from the pilot's API usage reports
(results/pilot_results.jsonl). Prices are entered by hand from each
provider's published pricing; update PRICES_CHECKED_ON when you re-check them.

Usage:
  python estimate_cost.py
"""

import json
from pathlib import Path
from statistics import mean

PILOT_RESULTS = Path("results/pilot_results.jsonl")

PRICES_CHECKED_ON = "2026-10-24"
# USD per million tokens
PRICES = {
    "cerebras": {"input": 0.35, "output": 0.75},  # inference-docs.cerebras.ai/models/openai-oss
    "together": {"input": 0.15, "output": 0.60},  # together.ai/pricing (serverless)
}

PAIRS_PER_TEST = 20
WARMUPS_PER_TEST = 1  # per service


def main():
    records = [json.loads(line) for line in PILOT_RESULTS.open(encoding="utf-8")]
    records = [r for r in records if not r["error"]]
    requests_per_test = PAIRS_PER_TEST + WARMUPS_PER_TEST

    print(f"Prices checked on {PRICES_CHECKED_ON}; {requests_per_test} requests per service per test\n")
    print(f"{'service':<10}{'test':<7}{'avg in':>8}{'avg out':>9}{'cost (USD)':>12}")

    grand_total = 0.0
    for service, price in PRICES.items():
        service_total = 0.0
        for test in ("short", "long"):
            runs = [r for r in records if r["service"] == service and r["test"] == test]
            avg_input = mean(r["prompt_tokens"] for r in runs)
            avg_output = mean(r["completion_tokens"] for r in runs)
            cost = requests_per_test * (
                avg_input * price["input"] + avg_output * price["output"]
            ) / 1_000_000
            service_total += cost
            print(f"{service:<10}{test:<7}{avg_input:>8.0f}{avg_output:>9.0f}{cost:>12.4f}")
        print(f"{service:<10}{'total':<7}{'':>17}{service_total:>12.4f}")
        grand_total += service_total

    print(f"\nEstimated total: ${grand_total:.4f}")


if __name__ == "__main__":
    main()

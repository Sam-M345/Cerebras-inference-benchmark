"""
Quality scoring (Phase 4): score every response against its checklist.

Reads results/benchmark_results.jsonl (never modified) and writes:
  results/benchmark_scored.jsonl   copy of every record plus quality fields
  results/spot_check.md            5 responses per service for Sam to review by hand

A response is flagged score_uncertain when it misses any checklist item,
because keyword matching is more likely to miss a correct answer than to
credit a wrong one.

Usage:
  python score.py
"""

import json
import random
import re
from pathlib import Path

RESULTS_DIR = Path("results")
PROMPTS_DIR = Path("prompts")
INPUT_FILE = RESULTS_DIR / "benchmark_results.jsonl"
OUTPUT_FILE = RESULTS_DIR / "benchmark_scored.jsonl"
SPOT_CHECK_FILE = RESULTS_DIR / "spot_check.md"
SPOT_CHECKS_PER_SERVICE = 5

HYPHENS_AND_SPACES = re.compile(r"[\u2010-\u2015\u2212\u00a0\u202f\u2009-]")
ABBREVIATIONS = re.compile(r"\b(i\.e\.|e\.g\.|approx\.|vs\.|etc\.)", re.IGNORECASE)


def normalize(text):
    """Lowercase, drop markdown and commas, turn hyphen variants into spaces."""
    text = text.lower().replace("*", "").replace("_", "").replace(",", "")
    text = HYPHENS_AND_SPACES.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def count_sentences(text):
    text = ABBREVIATIONS.sub("abbr", text.strip())
    return len(re.findall(r"[.!?]+(?=\s|$)", text))


def check_item(item, answer):
    if item["type"] == "keywords":
        normalized_answer = normalize(answer)
        return any(normalize(keyword) in normalized_answer for keyword in item["any_of"])
    if item["type"] == "sentence_count":
        return item["min"] <= count_sentences(answer) <= item["max"]
    raise ValueError(f"Unknown checklist item type: {item['type']}")


def score_record(record, checklists):
    items = checklists[record["test"]]["items"]
    if record["error"]:
        return {"quality_score": None, "quality_max": len(items), "checklist_hits": None, "score_uncertain": None}
    hits = {item["id"]: check_item(item, record["answer_text"]) for item in items}
    score = sum(hits.values())
    return {
        "quality_score": score,
        "quality_max": len(items),
        "checklist_hits": hits,
        "score_uncertain": score < len(items),
    }


def write_spot_check(records):
    rng = random.Random(0)
    lines = ["# Spot check", "", "For each response, confirm the automatic hits match your own reading.", ""]
    for service in ("cerebras", "together"):
        service_records = [r for r in records if r["service"] == service and r["quality_score"] is not None]
        uncertain = [r for r in service_records if r["score_uncertain"]]
        certain = [r for r in service_records if not r["score_uncertain"]]
        sample = uncertain[:SPOT_CHECKS_PER_SERVICE]
        sample += rng.sample(certain, min(SPOT_CHECKS_PER_SERVICE - len(sample), len(certain)))
        lines.append(f"## {service}")
        for r in sample:
            missed = [item_id for item_id, hit in r["checklist_hits"].items() if not hit]
            lines += [
                "",
                f"### {r['test']} | pair {r['pair_index'] + 1} | run {r['run_id']} | score {r['quality_score']}/{r['quality_max']}"
                + (f" | missed: {', '.join(missed)}" if missed else ""),
                "",
                "> " + r["answer_text"].strip().replace("\n", "\n> "),
                "",
                "Your verdict: ",
            ]
        lines.append("")
    SPOT_CHECK_FILE.write_text("\n".join(lines), encoding="utf-8")


def main():
    checklists = {
        test: json.loads((PROMPTS_DIR / f"{test}_checklist.json").read_text(encoding="utf-8"))
        for test in ("short", "long")
    }
    records = [json.loads(line) for line in INPUT_FILE.open(encoding="utf-8")]
    for record in records:
        record.update(score_record(record, checklists))

    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, default=str) + "\n")

    measured = [r for r in records if not r["is_warmup"] and r["quality_score"] is not None]
    write_spot_check(measured)

    print("test   service   | mean score | perfect | flagged uncertain")
    for test in ("short", "long"):
        for service in ("cerebras", "together"):
            runs = [r for r in measured if r["test"] == test and r["service"] == service]
            mean_score = sum(r["quality_score"] for r in runs) / len(runs)
            perfect = sum(r["quality_score"] == r["quality_max"] for r in runs)
            uncertain = sum(r["score_uncertain"] for r in runs)
            print(f"{test:<6} {service:<9} | {mean_score:.2f}/{runs[0]['quality_max']}     | {perfect}/{len(runs)}   | {uncertain}")
    print(f"\nScored copy: {OUTPUT_FILE}\nSpot check:  {SPOT_CHECK_FILE}")


if __name__ == "__main__":
    main()

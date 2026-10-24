r"""
Pilot benchmark: gpt-oss-120b on Cerebras vs. Together AI.

Purpose of the pilot (not the full benchmark):
  1. Confirm API access on both services.
  2. Confirm both accept identical settings.
  3. Discover which streaming fields, token counts, and cache fields each API exposes.
  4. Check that every planned metric is measurable (or mark it unavailable).

Setup (Windows PowerShell):
  .\.venv\Scripts\Activate.ps1
  Put CEREBRAS_API_KEY and TOGETHER_API_KEY in .env
  python pilot_benchmark.py

Outputs:
  results/pilot_results.jsonl   one record per request (metrics + raw usage)
  results/pilot_chunks.jsonl    first 15 and last 5 raw stream chunks per request (for field discovery)
  Console summary               fields seen, usage fields, metrics per run
"""

import json
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Services (both called directly, no routing layer)
# ---------------------------------------------------------------------------
SERVICES = {
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "model": "gpt-oss-120b",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": "TOGETHER_API_KEY",
        "model": "openai/gpt-oss-120b",
    },
}

# ---------------------------------------------------------------------------
# Matched settings (identical on both services)
# ---------------------------------------------------------------------------
SETTINGS = {
    "temperature": 1.0,
    "max_tokens": 2048,
    "reasoning_effort": "medium",
}

# Paired runs per test (each pair = one Cerebras + one Together request)
PILOT_PAIRS = {"short": 3, "long": 1}

PROMPTS_DIR = Path("prompts")
RESULTS_DIR = Path("results")

REASONING_KEYS = ("reasoning", "reasoning_content")  # checked in each delta
RAW_HEAD_CHUNKS = 15
RAW_TAIL_CHUNKS = 5


def load_prompt(test):
    return (PROMPTS_DIR / f"{test}.txt").read_text(encoding="utf-8").strip()


def make_client(service):
    cfg = SERVICES[service]
    key = os.environ.get(cfg["api_key_env"])
    if not key:
        raise SystemExit(f"Missing environment variable {cfg['api_key_env']}")
    return OpenAI(base_url=cfg["base_url"], api_key=key)


def to_dict(obj):
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


def run_request(client, service, test, prompt, run_id):
    """Send one streaming request and record chunk-level timing."""
    cfg = SERVICES[service]
    full_prompt = f"[run {run_id}]\n{prompt}"

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "test": test,
        "service": service,
        "model": cfg["model"],
        "run_id": run_id,
        "settings": SETTINGS,
        "error": None,
    }
    head_chunks = []
    tail_chunks = deque(maxlen=RAW_TAIL_CHUNKS)
    chunk_count = 0
    delta_keys_seen = set()
    first_reasoning_t = last_reasoning_t = None
    first_answer_t = last_answer_t = None
    reasoning_text, answer_text = [], []
    usage = None
    finish_reason = None

    t0 = time.perf_counter()
    try:
        stream = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": full_prompt}],
            stream=True,
            stream_options={"include_usage": True},
            **SETTINGS,
        )
        for chunk in stream:
            t = time.perf_counter() - t0
            chunk_dict = to_dict(chunk)
            saved_chunk = {"index": chunk_count, "t": round(t, 4), "chunk": chunk_dict}
            if chunk_count < RAW_HEAD_CHUNKS:
                head_chunks.append(saved_chunk)
            else:
                tail_chunks.append(saved_chunk)
            chunk_count += 1

            if chunk_dict.get("usage"):
                usage = chunk_dict["usage"]

            for choice in chunk_dict.get("choices") or []:
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
                delta = choice.get("delta") or {}
                delta_keys_seen.update(k for k, v in delta.items() if v)

                for rk in REASONING_KEYS:
                    if delta.get(rk):
                        reasoning_text.append(delta[rk])
                        if first_reasoning_t is None:
                            first_reasoning_t = t
                        last_reasoning_t = t

                if delta.get("content"):
                    answer_text.append(delta["content"])
                    if first_answer_t is None:
                        first_answer_t = t
                    last_answer_t = t

        total_t = time.perf_counter() - t0
    except Exception as e:  # record failures instead of stopping the pilot
        record["error"] = f"{type(e).__name__}: {e}"
        record["raw_chunks"] = head_chunks + list(tail_chunks)
        return record

    # Token counts from the API's own usage report (None = unavailable)
    prompt_tokens = (usage or {}).get("prompt_tokens")
    completion_tokens = (usage or {}).get("completion_tokens")
    details = (usage or {}).get("completion_tokens_details") or {}
    reasoning_tokens = details.get("reasoning_tokens")
    answer_tokens = (
        completion_tokens - reasoning_tokens
        if completion_tokens is not None and reasoning_tokens is not None
        else None
    )
    prompt_details = (usage or {}).get("prompt_tokens_details") or {}
    cached_tokens = prompt_details.get("cached_tokens")

    def window(first, last):
        return (last - first) if first is not None and last is not None else None

    def speed(tokens, secs):
        return round(tokens / secs, 1) if tokens and secs and secs > 0 else None

    reasoning_window = window(first_reasoning_t, last_reasoning_t)
    answer_window = window(first_answer_t, last_answer_t)

    record.update(
        {
            "finish_reason": finish_reason,
            "truncated": finish_reason == "length",
            "delta_keys_seen": sorted(delta_keys_seen),
            "first_reasoning_chunk_s": first_reasoning_t,
            "first_answer_chunk_s": first_answer_t,
            "reasoning_window_s": reasoning_window,
            "answer_window_s": answer_window,
            "total_s": total_t,
            "chunk_count": chunk_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "answer_tokens": answer_tokens,
            "reasoning_tok_per_s": speed(reasoning_tokens, reasoning_window),
            "answer_tok_per_s": speed(answer_tokens, answer_window),
            "cached_prompt_tokens": cached_tokens,
            "usage_raw": usage,
            "answer_text": "".join(answer_text),
            "reasoning_chars": len("".join(reasoning_text)),
            "raw_chunks": head_chunks + list(tail_chunks),
        }
    )
    return record


def fmt(v, digits=3):
    if v is None:
        return "unavailable"
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def main():
    load_dotenv()
    clients = {s: make_client(s) for s in SERVICES}
    prompts = {test: load_prompt(test) for test in PILOT_PAIRS}
    results = []

    for test, pair_count in PILOT_PAIRS.items():
        for i in range(pair_count):
            run_id = uuid.uuid4().hex[:8]  # same run ID for both requests in a pair
            order = ["cerebras", "together"] if i % 2 == 0 else ["together", "cerebras"]
            for service in order:
                print(f"{test} pair {i + 1}/{pair_count} | {service} | run {run_id} ...")
                results.append(run_request(clients[service], service, test, prompts[test], run_id))

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "pilot_results.jsonl", "w", encoding="utf-8") as f_res, open(
        RESULTS_DIR / "pilot_chunks.jsonl", "w", encoding="utf-8"
    ) as f_chunks:
        for r in results:
            f_chunks.write(
                json.dumps({"test": r["test"], "service": r["service"], "run_id": r["run_id"],
                            "raw_chunks": r.pop("raw_chunks", [])}, default=str) + "\n"
            )
            f_res.write(json.dumps(r, default=str) + "\n")

    print("\n================ PILOT SUMMARY ================")
    for service in SERVICES:
        runs = [r for r in results if r["service"] == service]
        print(f"\n--- {service} ---")
        keys = set().union(*(set(r.get("delta_keys_seen", [])) for r in runs))
        print(f"Delta fields seen:   {sorted(keys) or 'none'}")
        usage_fields = sorted(
            set().union(*(set((r.get("usage_raw") or {}).keys()) for r in runs))
        )
        print(f"Usage fields seen:   {usage_fields or 'unavailable'}")
        for r in runs:
            if r["error"]:
                print(f"  {r['test']} run {r['run_id']}: ERROR {r['error']}")
                continue
            print(
                f"  {r['test']} run {r['run_id']}: "
                f"prompt tokens {fmt(r['prompt_tokens'])} | "
                f"completion tokens {fmt(r['completion_tokens'])} | "
                f"first reasoning chunk {fmt(r['first_reasoning_chunk_s'])}s | "
                f"first answer chunk {fmt(r['first_answer_chunk_s'])}s | "
                f"total {fmt(r['total_s'])}s | "
                f"reasoning tok/s {fmt(r['reasoning_tok_per_s'])} | "
                f"answer tok/s {fmt(r['answer_tok_per_s'])} | "
                f"cached prompt tokens {fmt(r['cached_prompt_tokens'])} | "
                f"finish {r['finish_reason']}"
            )
    print("\nFull details: results/pilot_results.jsonl and results/pilot_chunks.jsonl")


if __name__ == "__main__":
    main()

"""
Retry check: were the delayed Cerebras requests hidden SDK retries?

The benchmark used the openai SDK default (max_retries=2), which silently
waits for a 429's retry-after header (up to 120 s) and retries. This sends
10 Cerebras-only short-prompt requests with max_retries=0 and logs each HTTP
status code plus any retry-after and rate-limit headers.

Writes results/retry_check.jsonl (existing results files are not touched).

Usage:
  python retry_check.py
"""

import json
import time
import uuid
from datetime import datetime, timezone

import openai
from dotenv import load_dotenv

from pilot_benchmark import RESULTS_DIR, SERVICES, SETTINGS, load_prompt, make_client, rate_limit_headers

REQUESTS = 10
PAUSE_S = 2
OUTPUT_FILE = RESULTS_DIR / "retry_check.jsonl"


def main():
    load_dotenv()
    cfg = SERVICES["cerebras"]
    client = make_client("cerebras")
    prompt = load_prompt("short")

    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for request_number in range(1, REQUESTS + 1):
            record = {"request_number": request_number, "timestamp_utc": datetime.now(timezone.utc).isoformat()}
            start = time.perf_counter()
            try:
                raw = client.chat.completions.with_raw_response.create(
                    model=cfg["model"],
                    messages=[{"role": "user", "content": f"[run {uuid.uuid4().hex[:8]}]\n{prompt}"}],
                    stream=True,
                    stream_options={"include_usage": True},
                    **SETTINGS,
                )
                record["status_code"] = raw.status_code
                record["headers"] = rate_limit_headers(raw.headers)
                for _ in raw.parse():
                    pass
                record["error"] = None
            except openai.APIStatusError as error:
                record["status_code"] = error.status_code
                record["headers"] = rate_limit_headers(error.response.headers)
                record["error"] = f"{type(error).__name__}: {error.message}"
            record["total_s"] = round(time.perf_counter() - start, 3)

            output.write(json.dumps(record) + "\n")
            output.flush()
            print(f"#{request_number:>2} status {record['status_code']} | {record['total_s']}s | {record['headers']}", flush=True)
            time.sleep(PAUSE_S)

    print(f"\nDetails: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

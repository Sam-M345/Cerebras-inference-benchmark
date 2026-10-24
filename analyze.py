"""
Analysis (Phase 5): statistics, summary table, and charts.

Reads results/benchmark_scored_v2.jsonl and results/manual_review_v2.json, then writes:
  results/summary.csv               one row per test and service
  charts/time_to_first_answer.png   chart 1
  charts/output_speed.png           chart 2
  charts/quality_score.png           chart 3
and prints a markdown table ready to paste into the article.

All measured requests are included in every statistic; warm-ups are excluded.
p95 is exploratory: with 20 runs it depends on the slowest one or two requests.

Usage:
  python analyze.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from estimate_cost import PRICES
from score import OUTPUT_FILE as SCORED_FILE

RESULTS_DIR = Path("results")
CHARTS_DIR = Path("charts")
MANUAL_REVIEW_FILE = RESULTS_DIR / "manual_review_v2.json"
SUMMARY_FILE = RESULTS_DIR / "summary.csv"

TESTS = ("short", "long")
SERVICES = ("cerebras", "together")
SERVICE_LABELS = {"cerebras": "Cerebras", "together": "Together AI"}
SERVICE_COLORS = {"cerebras": "#F05A28", "together": "#2F6FDE"}
TEST_LABELS = {"short": "Test A: short prompt (~100 tokens)", "long": "Test B: long prompt (~4,460 tokens)"}
DELAY_THRESHOLD_S = 10  # first answer chunk later than this counts as a delayed request
OUTPUT_SPEED_Y_MAX = 3500  # faster short-stream runs are chunk-timing artifacts; drawn as markers at the top edge

def load_measured():
    records = [json.loads(line) for line in SCORED_FILE.open(encoding="utf-8")]
    frame = pd.DataFrame(records)
    frame = frame[~frame["is_warmup"]].copy()
    frame["cost_usd"] = [
        (row.prompt_tokens * PRICES[row.service]["input"] + row.completion_tokens * PRICES[row.service]["output"]) / 1_000_000
        if pd.notna(row.prompt_tokens) and pd.notna(row.completion_tokens) else None
        for row in frame.itertuples()
    ]
    return frame


def summarize(frame, manual_verdicts):
    verdict_by_run = {(v["service"], v["run_id"]): v["verdict"] for v in manual_verdicts}
    rows = []
    for test in TESTS:
        for service in SERVICES:
            runs = frame[(frame["test"] == test) & (frame["service"] == service)]
            ok = runs[runs["error"].isna()]
            missed_verdicts = [verdict_by_run.get((service, run_id))
                               for run_id in ok[ok["quality_score"] < ok["quality_max"]]["run_id"]]
            row = {
                "test": test,
                "service": service,
                "runs": len(runs),
                "errors": len(runs) - len(ok),
                "http_429": int((runs["http_status"] == 429).sum()),
                "truncated": int(ok["truncated"].sum()),
                "empty_answers": int(ok["empty_answer"].sum()),
                "delayed_over_10s": int((ok["first_answer_chunk_s"] > DELAY_THRESHOLD_S).sum()),
            }
            for metric in ("first_answer_chunk_s", "total_s", "output_tok_per_s"):
                values = ok[metric].dropna()
                row[f"{metric}_median"] = values.median()
                row[f"{metric}_min"] = values.min()
                row[f"{metric}_max"] = values.max()
                row[f"{metric}_p5"] = values.quantile(0.05)
                row[f"{metric}_p95_exploratory"] = values.quantile(0.95)
            row["cost_usd_median"] = ok["cost_usd"].median()
            row["quality_mean_auto"] = ok["quality_score"].mean()
            row["quality_max"] = int(ok["quality_max"].iloc[0])
            row["quality_perfect_auto"] = int((ok["quality_score"] == ok["quality_max"]).sum())
            row["manual_scorer_false_negatives"] = missed_verdicts.count("correct")
            row["manual_substantive_misses"] = missed_verdicts.count("imperfect")
            row["manual_unreviewed_misses"] = missed_verdicts.count(None)
            row["correct_answers"] = row["quality_perfect_auto"] + row["manual_scorer_false_negatives"]
            rows.append(row)
    return pd.DataFrame(rows)


def markdown_table(summary):
    lines = [
        "| Test | Service | Median first answer chunk (s) [min–max] | Median output speed (tok/s) [5th–95th percentile] | Median total time (s) | Errors (429s) | Correct answers | Median cost per run |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in summary.itertuples():
        pending = f" ({row.manual_unreviewed_misses} pending review)" if row.manual_unreviewed_misses else ""
        lines.append(
            f"| {row.test} | {SERVICE_LABELS[row.service]} "
            f"| {row.first_answer_chunk_s_median:.2f} [{row.first_answer_chunk_s_min:.2f}–{row.first_answer_chunk_s_max:.2f}] "
            f"| {row.output_tok_per_s_median:,.0f} [{row.output_tok_per_s_p5:,.0f}–{row.output_tok_per_s_p95_exploratory:,.0f}] "
            f"| {row.total_s_median:.2f} "
            f"| {row.errors} ({row.http_429}) "
            f"| {row.correct_answers}/{row.runs}{pending} "
            f"| ${row.cost_usd_median:.5f} |"
        )
    return "\n".join(lines)


def count_phrase(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"


def strip_chart(frame, metric, title, y_label, output_path, y_max=None):
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.75), dpi=100, sharey=True, facecolor="white")
    for axis, test in zip(axes, TESTS):
        for position, service in enumerate(SERVICES):
            values = frame[(frame["test"] == test) & (frame["service"] == service) & frame["error"].isna()][metric].dropna()
            offsets = [position + ((i % 7) - 3) * 0.04 for i in range(len(values))]
            in_range = [(offset, value) for offset, value in zip(offsets, values) if y_max is None or value <= y_max]
            above_range = [(offset, value) for offset, value in zip(offsets, values) if y_max is not None and value > y_max]
            axis.scatter([offset for offset, _ in in_range], [value for _, value in in_range], s=45, alpha=0.75,
                         color=SERVICE_COLORS[service], edgecolor="black", linewidth=0.4, zorder=3)
            for offset, value in above_range:
                axis.scatter(offset, y_max, s=90, marker="^", color=SERVICE_COLORS[service],
                             edgecolor="black", linewidth=0.6, zorder=5, clip_on=False)
                axis.annotate(f"{value:,.0f} (timing artifact, see note)", (offset, y_max),
                              xytext=(12, -4), textcoords="offset points", va="top", fontsize=9, color="black")
            median = values.median()
            axis.hlines(median, position - 0.25, position + 0.25, color="black", linewidth=2.5, zorder=4)
            axis.annotate(f"median {median:,.2f}" if median < 100 else f"median {median:,.0f}",
                          (position + 0.27, median), va="center", fontsize=10, color="black")
            if metric == "first_answer_chunk_s":
                delayed = values[values > DELAY_THRESHOLD_S]
                if len(delayed):
                    low, high = int(delayed.min()), int(delayed.max())
                    span = f"{low} s" if low == high else f"{low}–{high} s"
                    noun = "request" if len(delayed) == 1 else "requests"
                    axis.annotate(
                        f"{len(delayed)} delayed {noun}\n({span} before first text)",
                        (position, delayed.min()), xytext=(position + 0.35, delayed.min() / 3),
                        fontsize=10, color="black", arrowprops={"arrowstyle": "->", "color": "black"},
                    )
        axis.set_xticks(range(len(SERVICES)), [SERVICE_LABELS[s] for s in SERVICES], fontsize=11)
        axis.set_xlim(-0.6, 1.9)
        axis.set_title(TEST_LABELS[test], fontsize=12)
        axis.grid(axis="y", color="#cccccc", linewidth=0.6, zorder=0)
        axis.set_facecolor("white")
    axes[0].set_ylim(0, y_max)
    axes[0].set_ylabel(y_label, fontsize=11)
    fig.suptitle(title, fontsize=15, fontweight="bold")
    fig.text(0.5, 0.01, "gpt-oss-120b, 20 runs per service per test, every run shown; black bar = median. "
             "Client-side timing includes network and queueing.", ha="center", fontsize=9, color="#333333")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(output_path, facecolor="white")
    plt.close(fig)


def quality_chart(frame, manual_verdicts, output_path):
    verdict_by_run = {(v["service"], v["run_id"]): v["verdict"] for v in manual_verdicts}
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.75), dpi=100, sharey=True, facecolor="white")
    for axis, test in zip(axes, TESTS):
        for position, service in enumerate(SERVICES):
            runs = frame[(frame["test"] == test) & (frame["service"] == service) & frame["error"].isna()]
            scores = (runs["quality_score"] / runs["quality_max"] * 100).dropna()
            offsets = [position + ((i % 7) - 3) * 0.04 for i in range(len(scores))]
            axis.scatter(offsets, scores, s=45, alpha=0.75, color=SERVICE_COLORS[service],
                         edgecolor="black", linewidth=0.4, zorder=3)
            mean_score = scores.mean()
            perfect_count = int((scores == 100).sum())
            axis.hlines(mean_score, position - 0.25, position + 0.25,
                        color="black", linewidth=2.5, zorder=4)
            missed = runs[runs["quality_score"] < runs["quality_max"]]
            verdicts = [verdict_by_run.get((service, run_id)) for run_id in missed["run_id"]]
            correct_after_review = perfect_count + verdicts.count("correct")
            axis.annotate(f"mean {mean_score:.0f}%", (position + 0.27, mean_score), va="center", fontsize=9, color="black")
            if correct_after_review == perfect_count:
                count_label = f"{perfect_count}/{len(scores)} perfect"
            else:
                count_label = (f"Automatic: {perfect_count}/{len(scores)} perfect /\n"
                               f"After review: {correct_after_review}/{len(scores)} correct")
            axis.annotate(count_label, (position, mean_score - 4), ha="center", va="top", fontsize=9, color="black")
            if len(missed):
                parts = [count_phrase(verdicts.count("imperfect"), "substantive miss", "substantive misses"),
                         count_phrase(verdicts.count("correct"), "scorer false negative", "scorer false negatives"),
                         f"{verdicts.count(None)} pending review"]
                axis.annotate(
                    "Manual review:\n" + "\n".join(part for part in parts if not part.startswith("0 ")),
                    (position + 0.15, scores.min()), xytext=(position - 0.55, scores.min() - 15),
                    fontsize=9, color="black", arrowprops={"arrowstyle": "->", "color": "black"},
                )
        axis.set_xticks(range(len(SERVICES)), [SERVICE_LABELS[s] for s in SERVICES], fontsize=11)
        axis.set_xlim(-0.6, 1.9)
        axis.set_ylim(0, 105)
        axis.set_title(TEST_LABELS[test], fontsize=12)
        axis.grid(axis="y", color="#cccccc", linewidth=0.6, zorder=0)
        axis.set_facecolor("white")
    axes[0].set_ylabel("Automatic checklist score (%)", fontsize=11)
    fig.suptitle("Answer quality (automatic checklist score)", fontsize=15, fontweight="bold")
    fig.text(
        0.5, 0.01,
        "gpt-oss-120b, 20 runs per service per test, every run shown; black bar = mean. "
        "Manual review is reported separately.",
        ha="center", fontsize=9, color="#333333",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(output_path, facecolor="white")
    plt.close(fig)


def main():
    frame = load_measured()
    manual_verdicts = json.loads(MANUAL_REVIEW_FILE.read_text(encoding="utf-8"))["verdicts"]
    summary = summarize(frame, manual_verdicts)
    summary.to_csv(SUMMARY_FILE, index=False)

    CHARTS_DIR.mkdir(exist_ok=True)
    strip_chart(frame, "first_answer_chunk_s", "Time to first answer chunk (lower is better)",
                "Seconds", CHARTS_DIR / "time_to_first_answer.png")
    strip_chart(frame, "output_tok_per_s", "Output speed (higher is better)",
                "Tokens per second", CHARTS_DIR / "output_speed.png", y_max=OUTPUT_SPEED_Y_MAX)
    quality_chart(frame, manual_verdicts, CHARTS_DIR / "quality_score.png")

    print(markdown_table(summary))
    print(f"\np95 values are exploratory and are in {SUMMARY_FILE}.")
    print(
        f"Charts: {CHARTS_DIR / 'time_to_first_answer.png'}, "
        f"{CHARTS_DIR / 'output_speed.png'}, {CHARTS_DIR / 'quality_score.png'}"
    )


if __name__ == "__main__":
    main()

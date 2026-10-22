"""Plot per-operation CDFs from current JSONL archives or API CSV exports."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics


def load_events(path):
    with open(path, encoding="utf-8", newline="") as source:
        if Path(path).suffix.lower() == ".csv":
            return list(csv.DictReader(source))
        return [json.loads(line) for line in source if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("plots"))
    parser.add_argument("--category")
    parser.add_argument("--label")
    args = parser.parse_args()
    groups = {}
    for record in load_events(args.input):
        if record.get("duration_seconds") in (None, ""):
            continue
        if args.category and record["category"] != args.category:
            continue
        if args.label and record["label"] != args.label:
            continue
        groups.setdefault((record["category"], record["label"]), []).append(record)
    if not groups:
        parser.error("No completed timing records match the filters")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    args.output.mkdir(parents=True, exist_ok=True)
    summary = []
    for (category, label), records in sorted(groups.items()):
        durations = sorted(float(r["duration_seconds"]) for r in records)
        count = len(durations)
        stats = {
            "category": category, "label": label, "count": count,
            "mean_seconds": statistics.mean(durations),
            "median_seconds": statistics.median(durations),
            "std_seconds": statistics.pstdev(durations),
            "min_seconds": min(durations), "max_seconds": max(durations),
            "failed_count": sum(r["status"] in {"failed", "partial_failure", "cancelled"}
                                for r in records),
        }
        summary.append(stats)
        figure, axis = plt.subplots(figsize=(9, 5))
        axis.step(durations, [(i + 1) / count for i in range(count)], where="post")
        axis.set(xlabel="Elapsed time (seconds)", ylabel="Empirical CDF",
                 title=f"{category}: {label}", ylim=(0, 1.05))
        axis.grid(True, alpha=0.3)
        axis.text(0.97, 0.06,
                  f"n={count}\nmean={stats['mean_seconds']:.6f}s\n"
                  f"median={stats['median_seconds']:.6f}s\nstd={stats['std_seconds']:.6f}s",
                  transform=axis.transAxes, ha="right", va="bottom")
        slug = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{category}_{label}")[:100]
        digest = hashlib.sha256(f"{category}:{label}".encode()).hexdigest()[:8]
        figure.tight_layout()
        figure.savefig(args.output / f"cdf_{slug}_{digest}.png", dpi=180)
        plt.close(figure)
    with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(f"Saved {len(groups)} CDF plots and summary.csv in {args.output}")


if __name__ == "__main__":
    main()

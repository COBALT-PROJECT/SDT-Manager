import csv
import json
import os
from pathlib import Path
import subprocess
import sys


def test_current_archive_generates_cdf_and_summary(tmp_path):
    archive = tmp_path / "events.jsonl"
    archive.write_text("\n".join(json.dumps({
        "category": "token_distribution", "label": "send_token_to_sdt",
        "duration_seconds": duration, "status": status,
    }) for duration, status in [(1.0, "completed"), (3.0, "failed")]) + "\n")
    output = tmp_path / "plots"
    script = Path(__file__).resolve().parents[1] / "plot_timestamps" / "plot_events.py"
    result = subprocess.run(
        [sys.executable, str(script), str(archive), "--output", str(output)],
        env=dict(os.environ, MPLCONFIGDIR=str(tmp_path / "matplotlib")),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(list(output.glob("*.png"))) == 1
    with (output / "summary.csv").open() as source:
        row = next(csv.DictReader(source))
    assert float(row["mean_seconds"]) == 2.0
    assert int(row["failed_count"]) == 1

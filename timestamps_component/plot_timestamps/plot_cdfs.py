import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ── Read data ────────────────────────────────────────────────────────
df = pd.read_excel("timestamps_results.xlsx")
df.columns = df.columns.str.strip()

# ── Compute totals ───────────────────────────────────────────────────
df["total instantiation"] = (
    df["instantiate sdt"]
    + df["instantiate ids-sdt"]
    + df["instantiate watchtower"]
)
df["total send token"] = (
    df["send token sdt"]
    + df["send token ids-sdt"]
    + df["send token watchtower"]
)


def plot_cdf(data, title, filename):
    """Plot a single empirical CDF with mean, median, std stats box."""
    sorted_data = np.sort(data.dropna())
    cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.step(sorted_data, cdf, where="post", linewidth=2, label=title)
    ax.set_xlabel("Time (seconds)", fontsize=13)
    ax.set_ylabel("CDF", fontsize=13)
    ax.set_title(f"CDF – {title}", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.05)

    # Stats box
    d = data.dropna()
    stats = (
        f"μ   = {d.mean():.4f}s\n"
        f"med = {d.median():.4f}s\n"
        f"σ   = {d.std():.4f}s"
    )
    props = dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.85,
                 edgecolor="gray")
    ax.text(0.97, 0.05, stats, transform=ax.transAxes, fontsize=10,
            verticalalignment="bottom", horizontalalignment="right",
            bbox=props, family="monospace")

    fig.tight_layout()
    fig.savefig(filename, dpi=200)
    print(f"Saved {filename}")
    plt.close(fig)


# ── Generate CDFs ────────────────────────────────────────────────────
plot_cdf(df["total instantiation"], "Total Instantiation Time",  "cdf_total_instantiation.png")
plot_cdf(df["total send token"],    "Total Send Token Time",     "cdf_total_send_token.png")
plot_cdf(df["register with AM"],    "Register with AM",          "cdf_register_am.png")

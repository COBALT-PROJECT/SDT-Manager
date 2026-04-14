import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ── Read data ────────────────────────────────────────────────────────
df = pd.read_excel("timestamps_results.xlsx")
df.columns = df.columns.str.strip()

# ── Plot CDF ─────────────────────────────────────────────────────────
col = "send BOM Certificate"
data = df[col].dropna()
sorted_data = np.sort(data)
cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)

fig, ax = plt.subplots(figsize=(8, 5))
ax.step(sorted_data, cdf, where="post", linewidth=2, label=col)
ax.set_xlabel("Time (seconds)", fontsize=13)
ax.set_ylabel("CDF", fontsize=13)
ax.set_title(f"CDF – {col}", fontsize=14)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)
ax.set_ylim(0, 1.05)

# Stats box
stats = (
    f"μ   = {data.mean():.4f}s\n"
    f"med = {data.median():.4f}s\n"
    f"σ   = {data.std():.4f}s"
)
props = dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.85,
             edgecolor="gray")
ax.text(0.97, 0.05, stats, transform=ax.transAxes, fontsize=10,
        verticalalignment="bottom", horizontalalignment="right",
        bbox=props, family="monospace")

fig.tight_layout()
fig.savefig("cdf_send_bom_certificate.png", dpi=200)
print("Saved cdf_send_bom_certificate.png")
plt.show()
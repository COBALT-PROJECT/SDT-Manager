import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── Data ──────────────────────────────────────────────────────────────────────
data = [
    2.3676, 2.3956, 2.4173, 2.3462, 2.3569,
    2.3603, 2.3315, 2.3349, 2.3752, 2.3352,
    2.3262, 2.3272, 2.3377, 2.3476, 2.3410,
    2.3408, 2.3202, 2.3391, 2.4024, 2.3506,
]

# ── Statistics ────────────────────────────────────────────────────────────────
sorted_data = np.sort(data)
n = len(sorted_data)
cdf = np.arange(1, n + 1) / n

mean_val   = np.mean(data)
median_val = np.median(data)

print(f"Mean:   {mean_val:.4f}s")
print(f"Median: {median_val:.4f}s")

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5.5))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

# CDF step line
ax.step(sorted_data, cdf, where="post",
        color="#3266ad", linewidth=2, label="CDF")
ax.scatter(sorted_data, cdf,
           color="#3266ad", s=30, zorder=5)

# Light fill under curve
ax.fill_between(sorted_data, cdf,
                step="post", alpha=0.08, color="#3266ad")

# Mean vertical line
ax.axvline(mean_val, color="#D85A30", linewidth=1.8,
           linestyle=(0, (6, 4)), label=f"Mean: {mean_val:.4f}s")

# Median vertical line
ax.axvline(median_val, color="#1D9E75", linewidth=1.8,
           linestyle=(0, (4, 4)), label=f"Median: {median_val:.4f}s")

# Mean label box
mean_cdf_y = float(cdf[sorted_data <= mean_val].max()) if any(sorted_data <= mean_val) else 0.0
ax.annotate(
    f"Mean: {mean_val:.4f}s",
    xy=(mean_val, 0.72),
    xytext=(mean_val, 0.72),
    ha="center", va="center",
    fontsize=10, fontweight="bold", color="white",
    bbox=dict(boxstyle="round,pad=0.3", facecolor="#D85A30", edgecolor="none"),
)

# Median label box
ax.annotate(
    f"Median: {median_val:.4f}s",
    xy=(median_val, 0.56),
    xytext=(median_val, 0.56),
    ha="center", va="center",
    fontsize=10, fontweight="bold", color="white",
    bbox=dict(boxstyle="round,pad=0.3", facecolor="#1D9E75", edgecolor="none"),
)

# ── Formatting ────────────────────────────────────────────────────────────────
ax.set_title("SDTM POST into CCM-Ledger",
             fontsize=15, fontweight="medium", pad=14)
ax.set_xlabel("Time taken (seconds)", fontsize=12)
ax.set_ylabel("CDF", fontsize=12)

ax.set_xlim(2.31, 2.43)
ax.set_ylim(0, 1.05)
ax.set_xticks(np.arange(2.31, 2.44, 0.01))
ax.set_xticklabels([f"{v:.2f}" for v in np.arange(2.31, 2.44, 0.01)],
                   fontsize=9)
ax.set_yticks(np.arange(0, 1.1, 0.1))
ax.set_yticklabels([f"{v:.1f}" for v in np.arange(0, 1.1, 0.1)], fontsize=9)

ax.grid(True, color="black", alpha=0.07, linewidth=0.6)
ax.spines[["top", "right"]].set_visible(False)
ax.spines[["left", "bottom"]].set_color("#cccccc")

# Custom legend
cdf_patch    = mpatches.Patch(color="#3266ad", label="CDF")
mean_patch   = mpatches.Patch(color="#D85A30", label=f"Mean: {mean_val:.4f}s")
median_patch = mpatches.Patch(color="#1D9E75", label=f"Median: {median_val:.4f}s")
ax.legend(handles=[cdf_patch, mean_patch, median_patch],
          fontsize=10, frameon=False, loc="upper left")

plt.tight_layout()

# ── Save ──────────────────────────────────────────────────────────────────────
output_path = "SDTM_POST_CCM_Ledger_CDF.png"
plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
print(f"Saved → {output_path}")
plt.show()
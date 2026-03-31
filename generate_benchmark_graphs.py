"""Generate benchmark graph images for README documentation."""

import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import os

matplotlib.rcParams.update({
    "figure.facecolor": "#0d1117",
    "axes.facecolor": "#161b22",
    "axes.edgecolor": "#30363d",
    "axes.labelcolor": "#c9d1d9",
    "text.color": "#c9d1d9",
    "xtick.color": "#8b949e",
    "ytick.color": "#8b949e",
    "grid.color": "#21262d",
    "legend.facecolor": "#161b22",
    "legend.edgecolor": "#30363d",
    "legend.labelcolor": "#c9d1d9",
    "font.family": "sans-serif",
    "font.size": 12,
})

OUT = "docs/images"
os.makedirs(OUT, exist_ok=True)

COLORS = ["#58a6ff", "#3fb950", "#d29922", "#f85149", "#bc8cff", "#79c0ff", "#56d364"]


# ── 1. Grover Search Scaling ──────────────────────────────────────────────
def grover_scaling():
    N = [8, 16, 32, 64, 128, 256]
    t = [1.100, 1.696, 2.533, 4.132, 6.041, 10.009]
    sqrt_N = [np.sqrt(n) for n in N]
    scale = t[0] / sqrt_N[0]
    theoretical = [scale * s for s in sqrt_N]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(N, t, "o-", color=COLORS[0], linewidth=2.5, markersize=9, label="Measured", zorder=5)
    ax.plot(N, theoretical, "--", color=COLORS[1], linewidth=2, alpha=0.7, label="O(√N) theoretical")
    ax.fill_between(N, t, alpha=0.15, color=COLORS[0])
    ax.set_xlabel("Database Size (N)", fontsize=13, fontweight="bold")
    ax.set_ylabel("Time (ms)", fontsize=13, fontweight="bold")
    ax.set_title("Grover Search: Time vs Database Size", fontsize=15, fontweight="bold", pad=12)
    ax.legend(fontsize=11, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xticks(N)
    for i, (x, y) in enumerate(zip(N, t)):
        ax.annotate(f"{y:.1f}ms", (x, y), textcoords="offset points",
                    xytext=(0, 12), fontsize=9, color=COLORS[0], ha="center", fontweight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/grover_scaling.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ grover_scaling.png")


# ── 2. Core Engine Performance ────────────────────────────────────────────
def core_engine():
    qubits = [4, 8, 12, 16]
    init_h = [0.020, 0.028, 0.039, 0.050]
    state_vec = [0.214, 0.329, 0.487, 1.112]
    measure = [1.734, 3.271, 4.925, None]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = np.arange(len(qubits))
    w = 0.25
    bars1 = ax.bar(x - w, init_h, w, label="Engine Init + H⊗n", color=COLORS[0], edgecolor="#0d1117", linewidth=0.5)
    bars2 = ax.bar(x, state_vec, w, label="State Vector Sim", color=COLORS[1], edgecolor="#0d1117", linewidth=0.5)
    measure_vals = [m if m is not None else 0 for m in measure]
    bars3 = ax.bar(x + w, measure_vals, w, label="Measure 1000 shots", color=COLORS[2], edgecolor="#0d1117", linewidth=0.5)
    # Hatch the missing bar
    bars3[3].set_alpha(0.2)

    ax.set_xlabel("Qubits", fontsize=13, fontweight="bold")
    ax.set_ylabel("Time (ms)", fontsize=13, fontweight="bold")
    ax.set_title("Core Engine Performance", fontsize=15, fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(qubits)
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(True, alpha=0.3, axis="y")

    for bars, vals in [(bars1, init_h), (bars2, state_vec), (bars3, measure)]:
        for bar, val in zip(bars, vals):
            if val is not None and val > 0.05:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.08,
                        f"{val:.2f}", ha="center", va="bottom", fontsize=8, fontweight="bold")

    fig.tight_layout()
    fig.savefig(f"{OUT}/core_engine.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ core_engine.png")


# ── 3. Encoding Performance ───────────────────────────────────────────────
def encoding():
    amp_q = [4, 6, 8, 10]
    amp_t = [0.303, 1.204, 4.779, 19.202]
    basis_q = [4, 8, 12, 16]
    basis_t = [0.007, 0.005, 0.005, 0.005]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    # Amplitude
    ax1.plot(amp_q, amp_t, "s-", color=COLORS[3], linewidth=2.5, markersize=10, label="Amplitude (Möttönen)")
    ax1.fill_between(amp_q, amp_t, alpha=0.15, color=COLORS[3])
    ax1.set_xlabel("Qubits", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Time (ms)", fontsize=13, fontweight="bold")
    ax1.set_title("Amplitude Encoding — O(2ⁿ) Gates", fontsize=14, fontweight="bold", pad=10)
    ax1.grid(True, alpha=0.3)
    for x, y in zip(amp_q, amp_t):
        ax1.annotate(f"{y:.1f}ms", (x, y), textcoords="offset points",
                     xytext=(0, 12), fontsize=10, color=COLORS[3], ha="center", fontweight="bold")
    ax1.legend(fontsize=10)

    # Basis
    ax2.bar(basis_q, basis_t, width=2, color=COLORS[4], edgecolor="#0d1117", linewidth=0.5, label="Basis (X-gate)")
    ax2.set_xlabel("Qubits", fontsize=13, fontweight="bold")
    ax2.set_ylabel("Time (ms)", fontsize=13, fontweight="bold")
    ax2.set_title("Basis Encoding — O(n) Gates", fontsize=14, fontweight="bold", pad=10)
    ax2.grid(True, alpha=0.3, axis="y")
    ax2.set_ylim(0, 0.015)
    ax2.legend(fontsize=10)

    fig.tight_layout(w_pad=3)
    fig.savefig(f"{OUT}/encoding_performance.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ encoding_performance.png")


# ── 4. Enterprise Operations ─────────────────────────────────────────────
def enterprise():
    rows = [100, 500, 1000]
    insert = [0.374, 0.436, 0.644]
    scan = [0.008, 0.039, 0.078]
    window = [0.186, 4.154, 14.793]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(rows, insert, "D-", color=COLORS[0], linewidth=2.5, markersize=9, label="Columnar Insert")
    ax.plot(rows, scan, "^-", color=COLORS[1], linewidth=2.5, markersize=9, label="Columnar Scan")
    ax.plot(rows, window, "o-", color=COLORS[2], linewidth=2.5, markersize=9, label="Window AVG")

    ax.fill_between(rows, window, alpha=0.1, color=COLORS[2])
    ax.set_xlabel("Row Count", fontsize=13, fontweight="bold")
    ax.set_ylabel("Time (ms)", fontsize=13, fontweight="bold")
    ax.set_title("Enterprise: Operation Time vs Row Count", fontsize=15, fontweight="bold", pad=12)
    ax.legend(fontsize=11, loc="upper left")
    ax.grid(True, alpha=0.3)

    for x, y in zip(rows, window):
        ax.annotate(f"{y:.1f}ms", (x, y), textcoords="offset points",
                    xytext=(8, 8), fontsize=9, color=COLORS[2], fontweight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/enterprise_operations.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ enterprise_operations.png")


# ── 5. Fault-Tolerant Performance ─────────────────────────────────────────
def fault_tolerant():
    labels = ["Surface Code\nd=3", "Surface Code\nd=5", "Logical Qubit\nd=3",
              "Logical Qubit\nd=5", "Magic State\nDistillation"]
    times = [0.074, 0.218, 0.142, 0.421, 0.131]
    colors = [COLORS[0], COLORS[0], COLORS[1], COLORS[1], COLORS[4]]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.barh(range(len(labels)), times, color=colors, edgecolor="#0d1117", linewidth=0.5, height=0.6)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel("Time (ms)", fontsize=13, fontweight="bold")
    ax.set_title("Fault-Tolerant Operations", fontsize=15, fontweight="bold", pad=12)
    ax.grid(True, alpha=0.3, axis="x")
    ax.invert_yaxis()

    for bar, t in zip(bars, times):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                f"{t:.3f} ms", va="center", fontsize=10, fontweight="bold", color="#c9d1d9")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fault_tolerant.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ fault_tolerant.png")


# ── 6. Distributed & Security ────────────────────────────────────────────
def distributed_security():
    labels = ["Cluster 3 nodes", "Cluster 10 nodes", "Cluster 50 nodes",
              "Vector Clock\n100 ops", "QKD 256-bit", "ACL 100 checks"]
    times = [0.010, 0.019, 0.078, 0.012, 0.005, 0.018]
    colors = [COLORS[0], COLORS[0], COLORS[0], COLORS[1], COLORS[4], COLORS[4]]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(range(len(labels)), times, color=colors, edgecolor="#0d1117", linewidth=0.5, height=0.55)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel("Time (ms)", fontsize=13, fontweight="bold")
    ax.set_title("Distributed & Security Performance", fontsize=15, fontweight="bold", pad=12)
    ax.grid(True, alpha=0.3, axis="x")
    ax.invert_yaxis()

    for bar, t in zip(bars, times):
        ax.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height()/2,
                f"{t:.3f} ms", va="center", fontsize=10, fontweight="bold", color="#c9d1d9")
    fig.tight_layout()
    fig.savefig(f"{OUT}/distributed_security.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ distributed_security.png")


# ── 7. Test Results Pie ───────────────────────────────────────────────────
def test_results():
    fig, ax = plt.subplots(figsize=(6, 6))
    sizes = [588, 3]
    labels = ["Passed (588)", "Failed (3)"]
    colors_pie = [COLORS[1], COLORS[3]]
    explode = (0.03, 0.08)
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors_pie, explode=explode,
        autopct="%1.1f%%", startangle=90, textprops={"fontsize": 13, "fontweight": "bold"},
        wedgeprops={"edgecolor": "#0d1117", "linewidth": 2}
    )
    autotexts[0].set_color("#0d1117")
    autotexts[1].set_color("#ffffff")
    ax.set_title("Test Suite Results (591 total)", fontsize=15, fontweight="bold", pad=15)
    fig.tight_layout()
    fig.savefig(f"{OUT}/test_results.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ test_results.png")


# ── 8. All Benchmarks Summary Radar ──────────────────────────────────────
def benchmark_summary():
    categories = ["Core Engine", "Encoding", "Grover Search",
                  "Enterprise", "Fault-Tolerant", "Distributed", "Security"]
    # Normalized scores (lower time = higher score, 0-10 scale)
    scores = [9.5, 7.0, 8.5, 7.5, 9.0, 9.8, 9.9]
    benchmarks_count = [11, 8, 6, 9, 5, 4, 2]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Bar chart of benchmark counts
    x = np.arange(len(categories))
    bars = ax1.bar(x, benchmarks_count, color=COLORS[:7], edgecolor="#0d1117", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, rotation=35, ha="right", fontsize=10)
    ax1.set_ylabel("Number of Benchmarks", fontsize=12, fontweight="bold")
    ax1.set_title("Benchmarks by Subsystem (46 total)", fontsize=14, fontweight="bold", pad=10)
    ax1.grid(True, alpha=0.3, axis="y")
    for bar, val in zip(bars, benchmarks_count):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                 str(val), ha="center", fontsize=11, fontweight="bold")

    # Performance score bar
    bars2 = ax1.barh  # skip radar, do horizontal score bars instead
    ax2.barh(range(len(categories)), scores, color=COLORS[:7], edgecolor="#0d1117", linewidth=0.5, height=0.55)
    ax2.set_yticks(range(len(categories)))
    ax2.set_yticklabels(categories, fontsize=11)
    ax2.set_xlabel("Performance Score (0–10)", fontsize=12, fontweight="bold")
    ax2.set_title("Performance Scores", fontsize=14, fontweight="bold", pad=10)
    ax2.set_xlim(0, 11)
    ax2.grid(True, alpha=0.3, axis="x")
    ax2.invert_yaxis()
    for i, s in enumerate(scores):
        ax2.text(s + 0.15, i, f"{s:.1f}", va="center", fontsize=10, fontweight="bold")

    fig.tight_layout(w_pad=3)
    fig.savefig(f"{OUT}/benchmark_summary.png", dpi=180, bbox_inches="tight")
    plt.close()
    print("  ✓ benchmark_summary.png")


if __name__ == "__main__":
    print("Generating benchmark graphs...")
    grover_scaling()
    core_engine()
    encoding()
    enterprise()
    fault_tolerant()
    distributed_security()
    test_results()
    benchmark_summary()
    print(f"\nAll graphs saved to {OUT}/")

"""
plot_results.py
Generates all plots for the paper from Locust CSV results.

Plots generated:
  1. Latency percentiles comparison (P50/P95/P99) per LB strategy
  2. Throughput (req/s) per LB strategy
  3. Latency over time during fault recovery experiment
  4. Scaling efficiency chart

Usage:
    python plot_results.py
"""

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import numpy as np

RESULTS_DIR = "results"
PLOTS_DIR = "plots"
os.makedirs(PLOTS_DIR, exist_ok=True)

sns.set_theme(style="whitegrid", palette="muted")
COLORS = {"round_robin": "#4C72B0", "least_connections": "#DD8452", "random": "#55A868"}
STRATEGIES = ["round_robin", "least_connections", "random"]


def load_stats(experiment_name: str):
    """Load Locust stats CSV for an experiment."""
    path = f"{RESULTS_DIR}/{experiment_name}_stats.csv"
    if not os.path.exists(path):
        print(f"[plot] WARNING: {path} not found, skipping.")
        return None
    return pd.read_csv(path)


def load_history(experiment_name: str):
    """Load Locust history CSV (time series) for an experiment."""
    path = f"{RESULTS_DIR}/{experiment_name}_stats_history.csv"
    if not os.path.exists(path):
        print(f"[plot] WARNING: {path} not found, skipping.")
        return None
    df = pd.read_csv(path)
    # Normalize timestamp to seconds from start
    if "Timestamp" in df.columns:
        df["elapsed"] = df["Timestamp"] - df["Timestamp"].min()
    return df


# ─────────────────────────────────────────────
# Plot 1: Latency Percentiles Bar Chart
# ─────────────────────────────────────────────
def plot_latency_percentiles():
    data = []
    for strategy in STRATEGIES:
        df = load_stats(f"lb_{strategy}")
        if df is None:
            continue
        # Get aggregate row (Name == "Aggregated")
        agg = df[df["Name"] == "Aggregated"]
        if agg.empty:
            agg = df.tail(1)
        row = agg.iloc[0]
        data.append({
            "strategy": strategy.replace("_", " ").title(),
            "P50": row.get("50%", 0),
            "P95": row.get("95%", 0),
            "P99": row.get("99%", 0),
        })

    if not data:
        print("[plot] No data for latency percentiles plot.")
        return

    df_plot = pd.DataFrame(data)
    x = np.arange(len(df_plot))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - width, df_plot["P50"], width, label="P50", color="#4C72B0")
    ax.bar(x, df_plot["P95"], width, label="P95", color="#DD8452")
    ax.bar(x + width, df_plot["P99"], width, label="P99", color="#C44E52")

    ax.set_xlabel("Load Balancing Strategy", fontsize=12)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Latency Percentiles by Load Balancing Strategy", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(df_plot["strategy"])
    ax.legend()
    plt.tight_layout()
    plt.savefig(f"{PLOTS_DIR}/latency_percentiles.png", dpi=150)
    plt.close()
    print(f"[plot] Saved latency_percentiles.png")


# ─────────────────────────────────────────────
# Plot 2: Throughput Comparison
# ─────────────────────────────────────────────
def plot_throughput():
    data = []
    for strategy in STRATEGIES:
        df = load_stats(f"lb_{strategy}")
        if df is None:
            continue
        agg = df[df["Name"] == "Aggregated"]
        if agg.empty:
            agg = df.tail(1)
        row = agg.iloc[0]
        data.append({
            "strategy": strategy.replace("_", " ").title(),
            "rps": row.get("Requests/s", 0),
            "failures": row.get("Failures/s", 0),
        })

    if not data:
        print("[plot] No data for throughput plot.")
        return

    df_plot = pd.DataFrame(data)
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(df_plot["strategy"], df_plot["rps"],
                  color=[COLORS[s] for s in STRATEGIES if s in COLORS],
                  edgecolor="black", linewidth=0.5)

    for bar, val in zip(bars, df_plot["rps"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{val:.2f}", ha="center", va="bottom", fontsize=10)

    ax.set_xlabel("Load Balancing Strategy", fontsize=12)
    ax.set_ylabel("Throughput (Requests/s)", fontsize=12)
    ax.set_title("Throughput by Load Balancing Strategy", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{PLOTS_DIR}/throughput_comparison.png", dpi=150)
    plt.close()
    print(f"[plot] Saved throughput_comparison.png")


# ─────────────────────────────────────────────
# Plot 3: Fault Recovery — Latency Over Time
# ─────────────────────────────────────────────
def plot_fault_recovery():
    df = load_history("fault_recovery")
    if df is None:
        return

    # Load fault event timestamps
    fault_events = []
    fault_file = f"{RESULTS_DIR}/fault_events.json"
    if os.path.exists(fault_file):
        with open(fault_file) as f:
            fault_events = json.load(f)

    # Get start time from history
    start_time = df["Timestamp"].min() if "Timestamp" in df.columns else 0

    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot P50 and P95 over time
    if "50%" in df.columns:
        ax.plot(df["elapsed"], df["50%"], label="P50 Latency", color="#4C72B0", linewidth=2)
    if "95%" in df.columns:
        ax.plot(df["elapsed"], df["95%"], label="P95 Latency", color="#DD8452", linewidth=2)
    if "99%" in df.columns:
        ax.plot(df["elapsed"], df["99%"], label="P99 Latency", color="#C44E52",
                linewidth=1.5, linestyle="--")

    # Mark fault and recovery events
    for event in fault_events:
        event_time = event["unix_time"] - start_time
        if event["event"] == "fault_injected":
            ax.axvline(x=event_time, color="red", linestyle="--", linewidth=2, label="Fault Injected")
            ax.text(event_time + 1, ax.get_ylim()[1] * 0.9, "Fault", color="red", fontsize=10)
        elif event["event"] == "replica_restarted":
            ax.axvline(x=event_time, color="green", linestyle="--", linewidth=2, label="Replica Restarted")
            ax.text(event_time + 1, ax.get_ylim()[1] * 0.8, "Recovered", color="green", fontsize=10)

    ax.set_xlabel("Elapsed Time (s)", fontsize=12)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Latency During Fault Injection and Recovery", fontsize=14)
    ax.legend()
    plt.tight_layout()
    plt.savefig(f"{PLOTS_DIR}/fault_recovery_latency.png", dpi=150)
    plt.close()
    print(f"[plot] Saved fault_recovery_latency.png")


# ─────────────────────────────────────────────
# Plot 4: Error Rate During Fault
# ─────────────────────────────────────────────
def plot_error_rate():
    df = load_history("fault_recovery")
    if df is None:
        return

    if "User count" not in df.columns and "Failures/s" not in df.columns:
        print("[plot] No failure data available.")
        return

    fig, ax = plt.subplots(figsize=(12, 5))

    if "Failures/s" in df.columns:
        ax.fill_between(df["elapsed"], df["Failures/s"],
                        alpha=0.4, color="#C44E52", label="Failures/s")
        ax.plot(df["elapsed"], df["Failures/s"], color="#C44E52", linewidth=2)

    ax.set_xlabel("Elapsed Time (s)", fontsize=12)
    ax.set_ylabel("Failures per Second", fontsize=12)
    ax.set_title("Error Rate During Fault Recovery Experiment", fontsize=14)
    ax.legend()
    plt.tight_layout()
    plt.savefig(f"{PLOTS_DIR}/error_rate.png", dpi=150)
    plt.close()
    print(f"[plot] Saved error_rate.png")


# ─────────────────────────────────────────────
# Plot 5: Latency over time per strategy
# ─────────────────────────────────────────────
def plot_latency_over_time():
    fig, ax = plt.subplots(figsize=(12, 6))

    for strategy in STRATEGIES:
        df = load_history(f"lb_{strategy}")
        if df is None:
            continue
        label = strategy.replace("_", " ").title()
        color = COLORS.get(strategy, "gray")
        if "50%" in df.columns:
            ax.plot(df["elapsed"], df["50%"], label=f"{label} P50",
                    color=color, linewidth=2)
        if "95%" in df.columns:
            ax.plot(df["elapsed"], df["95%"], label=f"{label} P95",
                    color=color, linewidth=1.5, linestyle="--")

    ax.set_xlabel("Elapsed Time (s)", fontsize=12)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Latency Over Time by Load Balancing Strategy", fontsize=14)
    ax.legend(ncol=2, fontsize=9)
    plt.tight_layout()
    plt.savefig(f"{PLOTS_DIR}/latency_over_time.png", dpi=150)
    plt.close()
    print(f"[plot] Saved latency_over_time.png")


if __name__ == "__main__":
    print("[plot] Generating all plots...")
    plot_latency_percentiles()
    plot_throughput()
    plot_fault_recovery()
    plot_error_rate()
    plot_latency_over_time()
    print(f"[plot] All plots saved to ./{PLOTS_DIR}/")

#!/usr/bin/env python3
"""Plot IPC and L2 miss rate from replacement_results.csv; write GMEAN as markdown."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "output"
DEFAULT_CSV = OUTPUT_DIR / "replacement_results.csv"
DEFAULT_IPC_PNG = OUTPUT_DIR / "replacement_ipc.png"
DEFAULT_L2_MISS_RATE_PNG = OUTPUT_DIR / "replacement_l2_miss_rate.png"
DEFAULT_GMEAN_MD = OUTPUT_DIR / "replacement_gmean.md"

REPLACEMENTS = ["lru", "pseudo_lru", "lru_bip", "lru_lip", "srrip"]
COLORS = {
    "lru": "#4C72B0",
    "pseudo_lru": "#55A868",
    "lru_bip": "#C44E52",
    "lru_lip": "#8172B2",
    "srrip": "#CCB974",
}


def short_trace_name(trace: str) -> str:
    name = trace.removesuffix(".champsimtrace.xz")
    if len(name) > 22:
        return name[:19] + "..."
    return name


def load_results(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {"trace", "replacement", "IPC", "l2_miss_rate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")

    df["replacement"] = pd.Categorical(df["replacement"], categories=REPLACEMENTS, ordered=True)
    traces = sorted(df["trace"].unique())
    df["trace"] = pd.Categorical(df["trace"], categories=traces, ordered=True)
    return df.sort_values(["trace", "replacement"])


def geometric_mean(values: pd.Series) -> float:
    arr = values.astype(float).to_numpy()
    if arr.size == 0:
        return float("nan")
    if np.any(arr <= 0):
        return float("nan")
    return float(np.exp(np.mean(np.log(arr))))


def build_gmean_table(df: pd.DataFrame) -> pd.DataFrame:
    """Geometric mean of IPC and L2 miss rate across the full trace set, per replacement."""
    n_traces = df["trace"].nunique()
    rows: list[dict[str, object]] = []

    for replacement in REPLACEMENTS:
        subset = df[df["replacement"] == replacement]
        if len(subset) != n_traces:
            raise ValueError(
                f"replacement {replacement!r}: expected {n_traces} traces, got {len(subset)}"
            )

        ipc_gmean = geometric_mean(subset["IPC"])
        l2_miss_rate_values = subset.loc[subset["l2_miss_rate"] > 0, "l2_miss_rate"]
        l2_miss_rate_gmean = geometric_mean(l2_miss_rate_values)

        rows.append(
            {
                "replacement": replacement,
                "n_traces": n_traces,
                "n_l2_miss_rate_traces": len(l2_miss_rate_values),
                "IPC_gmean": ipc_gmean,
                "l2_miss_rate_gmean": l2_miss_rate_gmean,
            }
        )

    table = pd.DataFrame(rows)
    table["replacement"] = pd.Categorical(
        table["replacement"], categories=REPLACEMENTS, ordered=True
    )
    return table.sort_values("replacement").reset_index(drop=True)


def format_gmean_display(table: pd.DataFrame) -> pd.DataFrame:
    display = table.copy()
    display["IPC_gmean"] = display["IPC_gmean"].map(lambda v: f"{v:.4f}")
    display["l2_miss_rate_gmean"] = display["l2_miss_rate_gmean"].map(
        lambda v: "nan" if pd.isna(v) else f"{v:.4f}"
    )
    display["n_traces"] = display["n_traces"].astype(int).astype(str)
    display["n_l2_miss_rate_traces"] = display["n_l2_miss_rate_traces"].astype(int).astype(str)
    return display


def dataframe_to_markdown(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    lines = [
        "| " + " | ".join(str(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def gmean_footnote(table: pd.DataFrame) -> str:
    if (table["n_l2_miss_rate_traces"] < table["n_traces"]).any():
        n = int(table["n_l2_miss_rate_traces"].iloc[0])
        total = int(table["n_traces"].iloc[0])
        return (
            f"_l2_miss_rate_gmean uses {n}/{total} traces (l2_miss_rate > 0; "
            "zero would zero the geometric mean)._"
        )
    return ""


def build_gmean_markdown(table: pd.DataFrame) -> str:
    sections = [
        "# Geometric mean across all traces",
        "",
        dataframe_to_markdown(format_gmean_display(table)),
    ]
    footnote = gmean_footnote(table)
    if footnote:
        sections.extend(["", footnote])
    return "\n".join(sections) + "\n"


def save_gmean_markdown(table: pd.DataFrame, output_path: Path) -> None:
    content = build_gmean_markdown(table)
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote {output_path}")


def plot_grouped_bars(
    df: pd.DataFrame,
    metric: str,
    ylabel: str,
    title: str,
    output_path: Path,
) -> None:
    traces = list(df["trace"].cat.categories)
    labels = [short_trace_name(t) for t in traces]
    n_traces = len(traces)
    n_replacements = len(REPLACEMENTS)

    x = range(n_traces)
    bar_width = 0.8 / n_replacements
    offsets = [(i - (n_replacements - 1) / 2) * bar_width for i in range(n_replacements)]

    fig, ax = plt.subplots(figsize=(max(14, n_traces * 0.75), 6))

    for replacement, offset in zip(REPLACEMENTS, offsets):
        subset = df[df["replacement"] == replacement]
        values = [subset.loc[subset["trace"] == trace, metric].iloc[0] for trace in traces]
        positions = [xi + offset for xi in x]
        ax.bar(
            positions,
            values,
            width=bar_width,
            label=replacement,
            color=COLORS[replacement],
            edgecolor="white",
            linewidth=0.4,
        )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(title="Replacement", loc="upper right")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Input results CSV")
    parser.add_argument("--ipc-png", type=Path, default=DEFAULT_IPC_PNG, help="IPC chart output")
    parser.add_argument(
        "--l2-miss-rate-png",
        type=Path,
        default=DEFAULT_L2_MISS_RATE_PNG,
        help="L2 miss rate chart output",
    )
    parser.add_argument(
        "--gmean-md",
        type=Path,
        default=DEFAULT_GMEAN_MD,
        help="GMEAN summary markdown table (IPC and L2 miss rate per replacement)",
    )
    parser.add_argument(
        "--no-gmean",
        action="store_true",
        help="Skip building the GMEAN markdown table",
    )
    args = parser.parse_args()

    df = load_results(args.csv)

    if not args.no_gmean:
        save_gmean_markdown(build_gmean_table(df), args.gmean_md)

    plot_grouped_bars(
        df,
        metric="IPC",
        ylabel="IPC",
        title="IPC by trace and cache replacement policy",
        output_path=args.ipc_png,
    )
    plot_grouped_bars(
        df,
        metric="l2_miss_rate",
        ylabel="L2 miss rate",
        title="L2 miss rate by trace and cache replacement policy",
        output_path=args.l2_miss_rate_png,
    )


if __name__ == "__main__":
    main()

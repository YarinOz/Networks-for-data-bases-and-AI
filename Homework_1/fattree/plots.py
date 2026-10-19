"""
plots.py -- figures for section 5 and 6 of the assignment.

Every function takes the plain list-of-dict rows produced by
`experiment.py` (or a k, for the topology drawing), writes a PNG and
returns its path. Nothing here recomputes anything, so you can re-style a
figure without re-running a slow sweep: load the CSV, pass the rows back in.

Plotting conventions used throughout (worth keeping if you restyle):
  * one y-axis per panel, never two scales on one plot -- quantities with
    different units go into separate panels;
  * a legend whenever more than one series is drawn, so colour is never the
    only thing distinguishing them;
  * the fault-free analytical baseline is drawn as a dashed reference line
    so the reader can see the stretch at a glance;
  * error bars are +/- one standard deviation across the independent trials,
    which is what makes the "is this bend real or is it noise?" question
    answerable.

-------------------------------------------------------------------------
WHERE TO EDIT
-------------------------------------------------------------------------
* PALETTE below is a four-colour categorical palette checked for
  colour-vision-deficiency separation. Replace it with your own if you
  like, but keep the colours far apart in lightness as well as hue.
* `plot_topology` draws tiers as rows; for k >= 8 it gets crowded, which is
  exactly why it defaults to k = 4 in the CLI. If you want a prettier
  picture, try drawing only one pod plus the core layer.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402

from .topology import (  # noqa: E402
    AGGREGATION,
    CORE,
    EDGE,
    HOST,
    build_fat_tree,
    nodes_of_tier,
)

# Categorical palette, assigned in fixed order (never cycled).
PALETTE = ["#2563EB", "#E8720C", "#14B8A6", "#9333EA"]
GRID_KW = dict(color="#D4D4D4", linewidth=0.8, alpha=0.7)
BASELINE_COLOR = "#6B7280"


def _style(ax, *, xlabel: str, ylabel: str, title: str) -> None:
    """Recessive axes + grid so the data is the loudest thing on the page."""
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.grid(True, **GRID_KW)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#9CA3AF")


def plot_failure_sweep(rows: list[dict], path: str | Path) -> Path:
    """Figure 1 -- average host-to-host path length vs link failure rate."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    x = [r["failure_rate"] for r in rows]
    y = [r["avg_path_len"] for r in rows]
    err = [r["avg_path_len_std"] for r in rows]
    baseline = rows[0]["avg_path_len_baseline"]
    k = rows[0]["k"]

    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    ax.axhline(
        baseline,
        color=BASELINE_COLOR,
        linestyle="--",
        linewidth=1.5,
        label=f"fault-free baseline ({baseline:.2f} hops)",
    )
    ax.errorbar(
        x, y, yerr=err,
        color=PALETTE[0], linewidth=2, marker="o", markersize=6,
        capsize=4, elinewidth=1.2,
        label="measured mean +/- 1 std",
    )
    _style(
        ax,
        xlabel="link failure probability p",
        ylabel="average path length (hops)",
        title=f"Average host-to-host path length under link failures (k={k})",
    )
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_connectivity(rows: list[dict], path: str | Path) -> Path:
    """Figure 2 -- what the path-length curve hides: how much of the network
    is still talking at all. Both series are fractions of the same kind, so
    they legitimately share one axis."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    x = [r["failure_rate"] for r in rows]
    reach = [r["reachability"] for r in rows]
    reach_err = [r["reachability_std"] for r in rows]
    isolated = [r["isolated_hosts"] for r in rows]
    k = rows[0]["k"]

    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    ax.errorbar(
        x, reach, yerr=reach_err,
        color=PALETTE[0], linewidth=2, marker="o", markersize=6,
        capsize=4, elinewidth=1.2, label="host pairs still connected",
    )
    ax.plot(
        x, isolated,
        color=PALETTE[1], linewidth=2, marker="s", markersize=6,
        label="hosts that lost their only uplink",
    )
    _style(
        ax,
        xlabel="link failure probability p",
        ylabel="fraction of hosts / host pairs",
        title=f"Connectivity loss under link failures (k={k})",
    )
    ax.set_ylim(-0.03, 1.03)
    ax.legend(frameon=False, loc="center left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_k_sweep(rows: list[dict], path: str | Path) -> Path:
    """Figure 3 -- scale effects at a fixed failure rate. Two panels because
    the two quantities have different units; never two y-axes on one panel."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ks = [r["k"] for r in rows]
    hosts = [r["hosts"] for r in rows]
    multi = [r["switches_multi_failure"] for r in rows]
    multi_err = [r.get("switches_multi_failure_std", 0.0) for r in rows]
    p = rows[0]["failure_rate"]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=160)

    axes[0].plot(ks, hosts, color=PALETTE[0], linewidth=2, marker="o", markersize=6)
    for kx, hy in zip(ks, hosts):
        axes[0].annotate(f"{hy:,}", (kx, hy), textcoords="offset points",
                         xytext=(0, 8), ha="center", fontsize=8, color="#374151")
    _style(axes[0], xlabel="switch port count k", ylabel="hosts supported",
           title="Network size scales as $k^3/4$")

    axes[1].errorbar(
        ks, multi, yerr=multi_err,
        color=PALETTE[1], linewidth=2, marker="s", markersize=6,
        capsize=4, elinewidth=1.2,
    )
    _style(axes[1], xlabel="switch port count k",
           ylabel="switches with >= 2 failed links",
           title=f"Multi-link failures at p={p:g}")

    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_topology(k: int, path: str | Path, *, show_hosts: bool = True) -> Path:
    """Figure 0 -- a picture of the generated graph, to prove by eye that the
    wiring rule does what the paper describes. Keep k small (4 or 6)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    g = build_fat_tree(k, with_hosts=show_hosts)
    tiers = [CORE, AGGREGATION, EDGE] + ([HOST] if show_hosts else [])
    colors = {CORE: PALETTE[3], AGGREGATION: PALETTE[0],
              EDGE: PALETTE[2], HOST: "#6B7280"}

    # Lay each tier out on its own horizontal row, evenly spaced.
    pos: dict[str, tuple[float, float]] = {}
    for row, tier in enumerate(tiers):
        nodes = sorted(nodes_of_tier(g, tier))
        n = len(nodes)
        y = len(tiers) - row
        for i, node in enumerate(nodes):
            pos[node] = ((i + 0.5) / n, y)

    fig, ax = plt.subplots(figsize=(min(2 + k * 1.6, 16), 5.5), dpi=160)
    for u, v in g.edges():
        (x1, y1), (x2, y2) = pos[u], pos[v]
        ax.plot([x1, x2], [y1, y2], color="#C9CDD4", linewidth=0.7, zorder=1)
    for tier in tiers:
        nodes = nodes_of_tier(g, tier)
        xs = [pos[n][0] for n in nodes]
        ys = [pos[n][1] for n in nodes]
        ax.scatter(xs, ys, s=70 if tier != HOST else 28,
                   color=colors[tier], zorder=2, label=f"{tier} ({len(nodes)})",
                   edgecolors="white", linewidths=1.0)

    ax.set_title(f"k = {k} fat-tree: {g.number_of_nodes()} nodes, "
                 f"{g.number_of_edges()} links",
                 loc="left", fontsize=12, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=4)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path

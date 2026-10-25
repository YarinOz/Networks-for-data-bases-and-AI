#!/usr/bin/env python3
"""
main.py -- command line entry point.

Sub-commands
------------
    build       generate a fat-tree, print its structure, optionally export it
    validate    run the structural self-checks (does my generator agree with
                the closed forms from the paper?)
    experiment  sweep the link failure rate, write CSV + figures
    scale       sweep k at a fixed failure rate, write CSV + figure
    compare     run the identical sweep over both topology variants (the
                controlled experiment) -> CSV + figure 4
    all         validate, then run every sweep and draw every figure

Input parameters (assignment section 3) -- all optional, all documented by
`--help`, and all overridable from a JSON config file (section 4):

    --k                 switch port count; the single structural parameter
    --failure-rate      link failure probability for a one-off run
    --rates             comma separated list of rates for the sweep
    --trials            independent random failure patterns per rate
    --seed              master seed; the whole run is reproducible from it
    --failure-mode      bernoulli (per-link coin flip) | exact (fixed count)
    --failure-scope     all | fabric | agg-core | edge-agg
    --pair-filter       all | cross-pod | intra-pod host pairs
    --sample-sources    measure from this many source hosts instead of all
    --variant           standard | thin-core (the control topology)
    --outdir            where CSVs and PNGs go

Examples
--------
    python main.py build --k 4
    python main.py validate --k 8
    python main.py experiment --k 8 --rates 0,0.02,0.05,0.1 --trials 20
    python main.py experiment --config config.example.json
    python main.py all --k 8

Precedence: built-in defaults < config file < command line flags.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from fattree import (
    VARIANTS,
    build_fat_tree,
    compare_variants,
    describe,
    fail_links,
    host_path_stats,
    switches_with_multiple_failures,
    sweep_failure_rate,
    sweep_k,
    theoretical_avg_path_length,
    validate_fat_tree,
    write_csv,
)
from fattree.plots import (
    plot_connectivity,
    plot_failure_sweep,
    plot_k_sweep,
    plot_topology,
    plot_variant_comparison,
)

DEFAULTS = {
    "k": 8,
    "failure_rate": 0.0,
    "rates": [0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3],
    "ks": [4, 6, 8, 10, 12, 16],
    "trials": 20,
    "seed": 1234,
    "failure_mode": "bernoulli",
    "failure_scope": "all",
    "pair_filter": "all",
    "sample_sources": None,
    "variant": "standard",
    "outdir": "results",
}


def load_config(path: str | None) -> dict:
    """Read a JSON config file and keep only the keys we understand."""
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    unknown = set(data) - set(DEFAULTS)
    if unknown:
        print(f"warning: ignoring unknown config keys: {sorted(unknown)}", file=sys.stderr)
    return {k: v for k, v in data.items() if k in DEFAULTS}


def parse_rates(value: str) -> list[float]:
    """--rates 0,0.01,0.05  or  --rates linspace:0,0.3,13"""
    value = value.strip()
    if value.startswith("linspace:"):
        start, stop, num = value[len("linspace:"):].split(",")
        start, stop, num = float(start), float(stop), int(num)
        step = (stop - start) / (num - 1) if num > 1 else 0.0
        return [round(start + i * step, 6) for i in range(num)]
    return [float(v) for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="k-ary fat-tree generator and failure analysis "
                    "(Al-Fares et al., SIGCOMM 2008).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command",
                        choices=["build", "validate", "experiment", "scale",
                                 "compare", "all"],
                        help="what to run")
    parser.add_argument("--config", help="JSON file with any of the options below")
    parser.add_argument("--k", type=int, help="switch port count (even, >= 2)")
    parser.add_argument("--failure-rate", type=float,
                        help="link failure probability for a single build")
    parser.add_argument("--rates", type=parse_rates,
                        help="sweep points, e.g. 0,0.05,0.1 or linspace:0,0.3,13")
    parser.add_argument("--ks", type=lambda s: [int(v) for v in s.split(",")],
                        help="k values for the scale sweep, e.g. 4,8,12,16")
    parser.add_argument("--trials", type=int, help="random failure patterns per point")
    parser.add_argument("--seed", type=int, help="master random seed")
    parser.add_argument("--failure-mode", choices=["bernoulli", "exact"])
    parser.add_argument("--failure-scope",
                        choices=["all", "fabric", "agg-core", "edge-agg"])
    parser.add_argument("--pair-filter", choices=["all", "cross-pod", "intra-pod"])
    parser.add_argument("--variant", choices=list(VARIANTS),
                        help="topology variant: 'standard' is the fat-tree of [1]; "
                             "'thin-core' keeps one uplink per aggregation switch "
                             "(the control topology)")
    parser.add_argument("--sample-sources", type=int,
                        help="measure from N source hosts instead of all of them")
    parser.add_argument("--outdir", help="directory for CSV and PNG output")
    parser.add_argument("--no-plots", action="store_true",
                        help="skip figure generation (CSV only)")
    return parser


def resolve_settings(args: argparse.Namespace) -> dict:
    """defaults < config file < explicit CLI flags."""
    settings = dict(DEFAULTS)
    settings.update(load_config(args.config))
    for key in DEFAULTS:
        value = getattr(args, key, None)
        if value is not None:
            settings[key] = value
    return settings


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_build(s: dict, make_plots: bool) -> None:
    g = build_fat_tree(s["k"], variant=s["variant"])
    info = describe(g)
    print(f"Fat-tree with k = {s['k']} (variant: {s['variant']})")
    for key, value in info.items():
        print(f"  {key:<18} {value}")
    print(f"  {'avg path length':<18} {theoretical_avg_path_length(s['k']):.4f} hops "
          f"(fault-free, analytical)")

    if s["failure_rate"] > 0:
        rng = random.Random(s["seed"])
        result = fail_links(g, s["failure_rate"], rng=rng,
                            mode=s["failure_mode"], scope=s["failure_scope"])
        stats = host_path_stats(result.graph, sample_sources=s["sample_sources"],
                                rng=rng, pair_filter=s["pair_filter"])
        print(f"\nAfter injecting {s['failure_rate']:.1%} link failures "
              f"(mode={s['failure_mode']}, scope={s['failure_scope']}, seed={s['seed']}):")
        print(f"  failed links       {result.num_failed} of {result.eligible_links} "
              f"({result.realised_rate:.2%})")
        print(f"  avg path length    {stats.avg_path_len:.4f} hops")
        print(f"  worst case         {stats.max_path_len} hops")
        print(f"  reachability       {stats.reachability:.4%} of host pairs")
        print(f"  isolated hosts     {stats.isolated_hosts:.4%}")
        print(f"  switches with >=2 failed links  "
              f"{switches_with_multiple_failures(result)}")

    if make_plots and s["k"] <= 6:
        out = plot_topology(s["k"],
                            Path(s["outdir"]) / f"topology_k{s['k']}_{s['variant']}.png",
                            variant=s["variant"])
        print(f"\nwrote {out}")


def cmd_validate(s: dict) -> None:
    validate_fat_tree(s["k"], variant=s["variant"])


def cmd_experiment(s: dict, make_plots: bool) -> None:
    print(f"Sweeping link failure rate, k={s['k']}, trials={s['trials']}, "
          f"seed={s['seed']}, mode={s['failure_mode']}, scope={s['failure_scope']}")
    rows = sweep_failure_rate(
        s["k"], s["rates"],
        trials=s["trials"], seed=s["seed"],
        mode=s["failure_mode"], scope=s["failure_scope"],
        sample_sources=s["sample_sources"], pair_filter=s["pair_filter"],
        variant=s["variant"],
    )
    csv_path = write_csv(rows, Path(s["outdir"]) / f"failure_sweep_k{s['k']}.csv")
    print(f"wrote {csv_path}")
    if make_plots:
        print("wrote", plot_failure_sweep(rows, Path(s["outdir"]) / f"fig1_path_length_k{s['k']}.png"))
        print("wrote", plot_connectivity(rows, Path(s["outdir"]) / f"fig2_connectivity_k{s['k']}.png"))


def cmd_compare(s: dict, make_plots: bool) -> None:
    """The controlled experiment: identical sweep, two topologies."""
    print(f"Comparing topology variants at k={s['k']}, trials={s['trials']}, "
          f"seed={s['seed']}, scope={s['failure_scope']}")
    results = compare_variants(
        s["k"], s["rates"],
        trials=s["trials"], seed=s["seed"],
        mode=s["failure_mode"], scope=s["failure_scope"],
        sample_sources=s["sample_sources"], pair_filter=s["pair_filter"],
    )
    flat = [row for rows in results.values() for row in rows]
    csv_path = write_csv(flat, Path(s["outdir"]) / f"variant_comparison_k{s['k']}.csv")
    print(f"wrote {csv_path}")
    if make_plots:
        print("wrote", plot_variant_comparison(
            results, Path(s["outdir"]) / f"fig4_variant_comparison_k{s['k']}.png"))


def cmd_scale(s: dict, make_plots: bool) -> None:
    rate = s["failure_rate"] or 0.01
    print(f"Sweeping k={s['ks']} at a fixed failure rate of {rate:.1%}")
    rows = sweep_k(
        s["ks"], p=rate, trials=s["trials"], seed=s["seed"],
        mode=s["failure_mode"], scope=s["failure_scope"],
        sample_sources=s["sample_sources"] or 32,
    )
    csv_path = write_csv(rows, Path(s["outdir"]) / "scale_sweep.csv")
    print(f"wrote {csv_path}")
    if make_plots:
        print("wrote", plot_k_sweep(rows, Path(s["outdir"]) / "fig3_scale.png"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    s = resolve_settings(args)
    make_plots = not args.no_plots
    Path(s["outdir"]).mkdir(parents=True, exist_ok=True)

    if args.command == "build":
        cmd_build(s, make_plots)
    elif args.command == "validate":
        cmd_validate(s)
    elif args.command == "experiment":
        cmd_experiment(s, make_plots)
    elif args.command == "scale":
        cmd_scale(s, make_plots)
    elif args.command == "compare":
        cmd_compare(s, make_plots)
    elif args.command == "all":
        cmd_validate(s)
        print()
        cmd_build(s, make_plots)
        print()
        if make_plots:
            print("wrote", plot_topology(4, Path(s["outdir"]) / "fig0_topology_k4.png"))
        print()
        cmd_experiment(s, make_plots)
        print()
        # The variant comparison deliberately runs with scope="fabric" over a
        # wider range of p. Host uplinks are identical in both variants and are
        # the dominant failure mode, so leaving them in would add the same large
        # effect to both curves and bury the one thing being measured. Holding
        # them constant is what makes this a controlled experiment rather than
        # two sweeps plotted on the same axes.
        cmd_compare(
            dict(s, failure_scope="fabric",
                 rates=[round(0.05 * i, 3) for i in range(13)]),
            make_plots,
        )
        print()
        cmd_scale(s, make_plots)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
experiment.py -- the sweep that produces the data for section 5.

Experimental design
-------------------
Independent variable : link failure probability p (the input parameter from
                       section 4 of the assignment).
Dependent variables  : average host-to-host shortest path length,
                       host-pair reachability,
                       fraction of isolated hosts,
                       number of switches that lost >= 2 links.
Controls             : k, failure mode, failure scope, host-pair filter.
Repetitions          : `trials` independent random failure patterns per p,
                       each with its own seed derived from one master seed,
                       so the whole figure is reproducible from a single
                       integer. Mean and standard deviation are reported.

The output is a list of plain dicts (one per p value) that is written to CSV
and handed to the plotting module. Keeping the data as rows, not as plot
objects, means you can re-plot or re-analyse without re-running the sweep --
runs for large k are the slow part.

"""

from __future__ import annotations

import csv
import math
import random
import statistics
from pathlib import Path

from .failures import fail_links, switches_with_multiple_failures
from .metrics import host_path_stats, theoretical_avg_path_length
from .topology import STANDARD, VARIANTS, build_fat_tree


def _mean_std(values: list[float]) -> tuple[float, float]:
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        return math.nan, 0.0
    mean = statistics.fmean(clean)
    std = statistics.stdev(clean) if len(clean) > 1 else 0.0
    return mean, std


def sweep_failure_rate(
    k: int,
    rates: list[float],
    *,
    trials: int = 10,
    seed: int = 1234,
    mode: str = "bernoulli",
    scope: str = "all",
    sample_sources: int | None = None,
    pair_filter: str = "all",
    variant: str = STANDARD,
    verbose: bool = True,
) -> list[dict]:
    """Main experiment: metrics vs link failure probability."""
    base = build_fat_tree(k, variant=variant)
    baseline = theoretical_avg_path_length(k)
    rows: list[dict] = []

    for p in rates:
        apl, reach, isolated, multi, realised = [], [], [], [], []

        for t in range(trials):
            # One deterministic sub-seed per (p, trial) so individual points
            # can be reproduced in isolation while debugging.
            rng = random.Random(f"{seed}-{p}-{t}")
            result = fail_links(base, p, rng=rng, mode=mode, scope=scope)
            stats = host_path_stats(
                result.graph,
                sample_sources=sample_sources,
                rng=rng,
                pair_filter=pair_filter,
            )
            apl.append(stats.avg_path_len)
            reach.append(stats.reachability)
            isolated.append(stats.isolated_hosts)
            multi.append(switches_with_multiple_failures(result))
            realised.append(result.realised_rate)

        apl_mean, apl_std = _mean_std(apl)
        reach_mean, reach_std = _mean_std(reach)
        iso_mean, _ = _mean_std(isolated)
        multi_mean, _ = _mean_std([float(m) for m in multi])
        realised_mean, _ = _mean_std(realised)

        row = {
            "k": k,
            "variant": variant,
            "failure_rate": p,
            "realised_failure_rate": realised_mean,
            "trials": trials,
            "avg_path_len": apl_mean,
            "avg_path_len_std": apl_std,
            "avg_path_len_baseline": baseline,
            "stretch": apl_mean / baseline if baseline else math.nan,
            "reachability": reach_mean,
            "reachability_std": reach_std,
            "isolated_hosts": iso_mean,
            "switches_multi_failure": multi_mean,
            "mode": mode,
            "scope": scope,
            "pair_filter": pair_filter,
            "sample_sources": sample_sources if sample_sources is not None else "all",
            "seed": seed,
        }
        rows.append(row)
        if verbose:
            print(
                f"  p={p:<6.3f} apl={apl_mean:6.3f} (+/-{apl_std:.3f}) "
                f"reach={reach_mean:6.3%} isolated={iso_mean:6.3%}"
            )

    return rows


def compare_variants(
    k: int,
    rates: list[float],
    *,
    variants: tuple[str, ...] = VARIANTS,
    verbose: bool = True,
    **kwargs,
) -> dict[str, list[dict]]:
    """Run the identical failure sweep over several topology variants.

    This is the controlled experiment. Both networks have the same k, the same
    k^3/4 hosts, the same pods, the same edge<->aggregation layer and the same
    per-link failure probability; the only thing that differs is how many
    equal-cost paths exist between pods. Any gap between the resulting curves
    is therefore attributable to path diversity and to nothing else.

    One honest caveat to state when presenting the result: the thin-core
    network has fewer links (k^2/2 instead of k^3/4 in the top layer), so at a
    given p it suffers fewer failures in absolute terms. That confound works
    *against* the hypothesis -- the crippled topology is handed an advantage
    and still degrades faster -- so it strengthens rather than weakens the
    conclusion.

    Returns {variant: rows}, ready for `plots.plot_variant_comparison`.
    """
    results: dict[str, list[dict]] = {}
    for variant in variants:
        if verbose:
            print(f"  -- variant: {variant}")
        results[variant] = sweep_failure_rate(
            k, rates, variant=variant, verbose=verbose, **kwargs
        )
    return results


def sweep_k(
    ks: list[int],
    *,
    p: float = 0.01,
    trials: int = 10,
    seed: int = 1234,
    mode: str = "bernoulli",
    scope: str = "all",
    sample_sources: int | None = 32,
    verbose: bool = True,
) -> list[dict]:
    """Secondary experiment: metrics vs switch port count at a fixed failure
    rate. Covers the "basic" (hosts vs k) and "intermediate" (switches with
    multiple failed links vs k) metrics from the assignment sheet."""
    rows: list[dict] = []
    for k in ks:
        g = build_fat_tree(k)
        apl, reach, multi = [], [], []
        for t in range(trials):
            rng = random.Random(f"{seed}-k{k}-{t}")
            result = fail_links(g, p, rng=rng, mode=mode, scope=scope)
            stats = host_path_stats(result.graph, sample_sources=sample_sources, rng=rng)
            apl.append(stats.avg_path_len)
            reach.append(stats.reachability)
            multi.append(float(switches_with_multiple_failures(result)))

        apl_mean, apl_std = _mean_std(apl)
        reach_mean, reach_std = _mean_std(reach)
        multi_mean, multi_std = _mean_std(multi)
        rows.append({
            "k": k,
            "hosts": k ** 3 // 4,
            "switches": 5 * k ** 2 // 4,
            "links": 3 * k ** 3 // 4,
            "failure_rate": p,
            "trials": trials,
            "avg_path_len": apl_mean,
            "avg_path_len_std": apl_std,
            "reachability": reach_mean,
            "reachability_std": reach_std,
            "switches_multi_failure": multi_mean,
            "switches_multi_failure_std": multi_std,
            "seed": seed,
        })
        if verbose:
            print(
                f"  k={k:<3d} hosts={k**3//4:<6d} apl={apl_mean:6.3f} "
                f"reach={reach_mean:7.3%} multi-fail switches={multi_mean:.1f}"
            )
    return rows


def write_csv(rows: list[dict], path: str | Path) -> Path:
    """Dump rows to CSV so results survive outside the process."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return path
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path

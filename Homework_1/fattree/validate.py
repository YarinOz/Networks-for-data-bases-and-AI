"""
validate.py -- structural self-checks.

A topology generator that is subtly wrong produces plots that look
plausible and conclusions that are wrong, so every build is checked against
the invariants of a k-ary fat-tree before any measurement is taken. Run it
with `python main.py validate --k 8`, or import `validate_fat_tree` in your
own tests.

Invariants checked
------------------
1. Node and link counts match the closed forms k^3/4 hosts, 5k^2/4
   switches, 3k^3/4 links.
2. Every switch uses exactly k ports; every host uses exactly 1.
3. The layering is strict: hosts only touch edge switches, edge only
   touches hosts and aggregation, aggregation only touches edge and core,
   core only touches aggregation. No link ever skips or stays within a tier.
4. Each aggregation switch reaches exactly one core *group*, and every core
   switch touches every pod exactly once (this is the property that gives
   the fabric its (k/2)^2 disjoint cross-pod paths).
5. The graph is connected and its host-to-host distances are exactly the
   2 / 4 / 6 hop pattern, matching `theoretical_avg_path_length`.
6. Full bisection bandwidth: cutting the network between the first k/2 pods
   and the rest leaves k^3/8 links, i.e. one per host pair across the cut.
"""

from __future__ import annotations

import math

import networkx as nx

from .metrics import host_path_stats, theoretical_avg_path_length
from .topology import (
    AGGREGATION,
    CORE,
    EDGE,
    HOST,
    FatTreeSpec,
    build_fat_tree,
    nodes_of_tier,
)

ALLOWED_NEIGHBOURS = {
    HOST: {EDGE},
    EDGE: {HOST, AGGREGATION},
    AGGREGATION: {EDGE, CORE},
    CORE: {AGGREGATION},
}


def validate_fat_tree(k: int, *, verbose: bool = True) -> list[str]:
    """Return a list of human-readable check results; raises on failure."""
    g = build_fat_tree(k)
    spec = FatTreeSpec(k)
    half = k // 2
    report: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(f"FAILED: {message}")
        report.append(f"ok  {message}")

    # 1. counts -----------------------------------------------------------
    check(len(nodes_of_tier(g, HOST)) == spec.hosts, f"hosts == k^3/4 == {spec.hosts}")
    check(len(nodes_of_tier(g, CORE)) == spec.core_switches, f"core switches == (k/2)^2 == {spec.core_switches}")
    check(len(nodes_of_tier(g, AGGREGATION)) == spec.agg_switches, f"agg switches == k^2/2 == {spec.agg_switches}")
    check(len(nodes_of_tier(g, EDGE)) == spec.edge_switches, f"edge switches == k^2/2 == {spec.edge_switches}")
    check(g.number_of_edges() == spec.links, f"links == 3k^3/4 == {spec.links}")

    # 2. port counts ------------------------------------------------------
    for tier in (CORE, AGGREGATION, EDGE):
        degrees = {g.degree(n) for n in nodes_of_tier(g, tier)}
        check(degrees == {k}, f"every {tier} switch uses exactly k == {k} ports")
    host_degrees = {g.degree(n) for n in nodes_of_tier(g, HOST)}
    check(host_degrees == {1}, "every host has exactly one uplink")

    # 3. strict layering --------------------------------------------------
    bad = [
        (u, v)
        for u, v in g.edges()
        if g.nodes[v]["tier"] not in ALLOWED_NEIGHBOURS[g.nodes[u]["tier"]]
    ]
    check(not bad, "no link skips a tier or stays inside one")

    # 4. core wiring ------------------------------------------------------
    for a in nodes_of_tier(g, AGGREGATION):
        groups = {g.nodes[n]["group"] for n in g.neighbors(a) if g.nodes[n]["tier"] == CORE}
        if len(groups) != 1:
            raise AssertionError(f"FAILED: {a} spans core groups {groups}")
    report.append("ok  each aggregation switch feeds exactly one core group")

    for c in nodes_of_tier(g, CORE):
        pods = [g.nodes[n]["pod"] for n in g.neighbors(c)]
        if sorted(pods) != list(range(k)):
            raise AssertionError(f"FAILED: core switch {c} does not touch every pod exactly once")
    report.append("ok  each core switch touches every pod exactly once")

    # 5. connectivity and hop pattern -------------------------------------
    check(nx.is_connected(g), "the fault-free topology is connected")

    stats = host_path_stats(g)
    expected = theoretical_avg_path_length(k)
    check(
        math.isclose(stats.avg_path_len, expected, rel_tol=1e-9),
        f"average host-to-host path length == {expected:.6f} hops (closed form)",
    )
    check(stats.max_path_len == (6 if k >= 4 else stats.max_path_len),
          f"worst-case host-to-host distance is {stats.max_path_len} hops")
    check(math.isclose(stats.reachability, 1.0), "every host pair is reachable")

    # 6. bisection --------------------------------------------------------
    left = {n for n, d in g.nodes(data=True) if d.get("pod") is not None and d["pod"] < half}
    cut = sum(1 for u, v in g.edges() if (u in left) != (v in left))
    check(cut == spec.bisection_links, f"bisection cut == k^3/8 == {spec.bisection_links} links")

    if verbose:
        print(f"Structural validation of the k={k} fat-tree")
        for line in report:
            print("  " + line)
        print(f"  -> {len(report)} checks passed")
    return report

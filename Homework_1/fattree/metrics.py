"""
metrics.py -- the quantitative measurements taken on a (possibly damaged)
topology.

The headline metric for this project is the **average host-to-host shortest
path length**, measured in hops, as a function of the link failure rate.
A fault-free k-ary fat-tree has a very boring path length distribution:

    same edge switch          2 hops   (host -> edge -> host)
    same pod, different edge  4 hops   (host -> edge -> agg -> edge -> host)
    different pods            6 hops   (host -> edge -> agg -> core -> agg -> edge -> host)

so the fault-free average is a fixed number just under 6 for any sizeable k.
Failures can only make paths longer (a detour) or impossible (disconnection),
and the interesting part is *how the two effects trade off*: the fat-tree has
so much path diversity in the fabric that for a long time failures cause
almost no stretch at all, and then the curve bends sharply once the single
host uplinks start dying.

Because of that, the module reports three numbers for every measurement and
you should always read them together:

    avg_path_len   mean hops over host pairs that are *still connected*
    reachability   fraction of host pairs that remain connected
    isolated_hosts fraction of hosts that lost their only uplink

Reporting avg_path_len alone is misleading -- it can even go *down* under
heavy failures, because the long cross-pod pairs are the first to be cut and
only the short intra-rack pairs survive. That observation is worth a
paragraph in the README.

-------------------------------------------------------------------------
WHERE TO EDIT
-------------------------------------------------------------------------
* `host_path_stats` is a plain BFS sweep. Swap in a different question:
  weighted links (nx.single_source_dijkstra_length), path *count* instead
  of path length (see `count_shortest_paths`), or restrict the host pairs
  to cross-pod ones only (`pair_filter`) which isolates the core layer's
  contribution.
* `sample_sources` trades accuracy for speed. For k <= 8 just measure
  every pair; for k >= 16 sampling a few dozen sources is plenty, and the
  experiment module reports the standard deviation across trials so you can
  see whether your sample size is big enough.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

import networkx as nx

from .topology import HOST, hosts as all_hosts


@dataclass
class PathStats:
    """Result of one measurement on one (damaged) graph."""

    avg_path_len: float          # mean hops over connected host pairs
    max_path_len: int            # worst case hops observed
    reachability: float          # connected host pairs / measured host pairs
    isolated_hosts: float        # fraction of hosts with no surviving link
    measured_pairs: int          # how many ordered pairs we actually looked at
    connected_pairs: int

    def as_dict(self) -> dict:
        return asdict(self)


def host_path_stats(
    g: nx.Graph,
    *,
    sample_sources: int | None = None,
    rng: random.Random | None = None,
    pair_filter: str = "all",
) -> PathStats:
    """BFS from (a sample of) hosts and summarise host-to-host distances.

    pair_filter
        "all"        every ordered host pair (default)
        "cross-pod"  only pairs whose hosts sit in different pods -- these
                     are the pairs that must traverse the core layer
        "intra-pod"  only pairs inside the same pod
    """
    rng = rng or random.Random()

    hosts = all_hosts(g)
    if len(hosts) < 2:
        return PathStats(math.nan, 0, 0.0, 0.0, 0, 0)

    pods = {h: g.nodes[h]["pod"] for h in hosts}
    host_set = set(hosts)

    sources = hosts
    if sample_sources is not None and sample_sources < len(hosts):
        sources = rng.sample(hosts, sample_sources)

    total_pairs = 0
    connected_pairs = 0
    hop_sum = 0
    hop_max = 0

    for s in sources:
        # BFS over the damaged graph; unreachable nodes simply do not appear.
        lengths = nx.single_source_shortest_path_length(g, s)
        for t in hosts:
            if t == s:
                continue
            if not _pair_wanted(pods[s], pods[t], pair_filter):
                continue
            total_pairs += 1
            d = lengths.get(t)
            if d is not None:
                connected_pairs += 1
                hop_sum += d
                hop_max = max(hop_max, d)

    isolated = sum(1 for h in hosts if g.degree(h) == 0) / len(hosts)

    return PathStats(
        avg_path_len=(hop_sum / connected_pairs) if connected_pairs else math.nan,
        max_path_len=hop_max,
        reachability=(connected_pairs / total_pairs) if total_pairs else 0.0,
        isolated_hosts=isolated,
        measured_pairs=total_pairs,
        connected_pairs=connected_pairs,
    )


def _pair_wanted(pod_s: int, pod_t: int, pair_filter: str) -> bool:
    if pair_filter == "all":
        return True
    if pair_filter == "cross-pod":
        return pod_s != pod_t
    if pair_filter == "intra-pod":
        return pod_s == pod_t
    raise ValueError(f"unknown pair_filter {pair_filter!r}")


def count_shortest_paths(g: nx.Graph, source: str, target: str) -> int:
    """Number of distinct shortest paths between two hosts.

    In a healthy fat-tree this is (k/2)^2 for a cross-pod pair and k/2 for a
    cross-rack same-pod pair -- a direct measure of the path diversity that
    makes the topology fault tolerant. Exposed here as a hook for anyone who
    wants to plot "surviving equal-cost paths vs failure rate" instead of
    path length.
    """
    try:
        return sum(1 for _ in nx.all_shortest_paths(g, source, target))
    except nx.NetworkXNoPath:
        return 0


def theoretical_avg_path_length(k: int) -> float:
    """Closed form for the fault-free average over all ordered host pairs.

    Fix a source host. Of the other k^3/4 - 1 hosts:
        k/2 - 1          share its edge switch        -> 2 hops
        (k/2 - 1)(k/2)   share its pod, other rack    -> 4 hops
        rest                                           -> 6 hops
    Useful as a baseline line on the plot and as a self-check: the measured
    value at p = 0 must match this exactly.
    """
    half = k // 2
    total = k ** 3 // 4 - 1
    same_edge = half - 1
    same_pod = (half - 1) * half
    cross_pod = total - same_edge - same_pod
    return (2 * same_edge + 4 * same_pod + 6 * cross_pod) / total

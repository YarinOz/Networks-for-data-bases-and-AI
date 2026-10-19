"""
topology.py -- construction of a k-ary fat-tree.

The structure follows:
    M. Al-Fares, A. Loukissas, A. Vahdat,
    "A scalable, commodity data center network architecture",
    SIGCOMM CCR 38(4), 2008.

Design recap (everything here is derived from a single parameter k, the
number of ports on every switch -- all switches are identical commodity
switches, which is the whole point of the paper):

    * k pods.
    * Each pod holds k/2 EDGE switches and k/2 AGGREGATION switches,
      wired as a complete bipartite graph inside the pod.
    * Each edge switch uses k/2 ports downwards for hosts and k/2 ports
      upwards to the aggregation layer.
    * (k/2)^2 CORE switches, arranged as k/2 "groups" of k/2 switches.
      Aggregation switch number a of *every* pod connects to all k/2 core
      switches of group a. A core switch therefore has exactly k ports,
      one per pod.

    hosts     = k^3 / 4
    switches  = 5 k^2 / 4          (k^2/4 core + k^2/2 agg + k^2/2 edge)
    links     = 3 k^3 / 4          (k^3/4 host + k^3/4 edge-agg + k^3/4 agg-core)

k must be even (a switch splits its ports evenly between up and down).

-------------------------------------------------------------------------
WHERE TO EDIT
-------------------------------------------------------------------------
* `_wire_core_layer` is the only place that decides which aggregation
  switch talks to which core switch. Swap that rule and you get a
  different (possibly broken, possibly interesting) topology -- a good
  place to experiment.
* Node names are produced by the `*_name` helpers. Change them freely;
  nothing else in the project parses names, everything reads the node
  attributes instead.
* Every node carries attributes: tier, pod, index and the paper's IP
  address. Add your own attributes here (e.g. a per-switch failure
  domain, a rack id, a cost) and the metrics module can use them.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

# ---------------------------------------------------------------------------
# Tier labels. Used as the "tier" node attribute everywhere else.
# ---------------------------------------------------------------------------
CORE = "core"
AGGREGATION = "aggregation"
EDGE = "edge"
HOST = "host"

SWITCH_TIERS = (CORE, AGGREGATION, EDGE)

# Link "kind" attribute -- which two tiers a link joins.
HOST_LINK = "host-edge"
EDGE_AGG_LINK = "edge-agg"
AGG_CORE_LINK = "agg-core"


# ---------------------------------------------------------------------------
# Naming helpers. Human-readable and stable; indices are 0-based internally.
# ---------------------------------------------------------------------------
def core_name(group: int, index: int) -> str:
    """Core switch `index` inside core group `group` (both 0-based)."""
    return f"core-{group}-{index}"


def agg_name(pod: int, index: int) -> str:
    """Aggregation switch `index` (0-based) of pod `pod`."""
    return f"agg-{pod}-{index}"


def edge_name(pod: int, index: int) -> str:
    """Edge (top-of-rack) switch `index` (0-based) of pod `pod`."""
    return f"edge-{pod}-{index}"


def host_name(pod: int, edge_index: int, index: int) -> str:
    """Host `index` hanging off edge switch `edge_index` of pod `pod`."""
    return f"host-{pod}-{edge_index}-{index}"


# ---------------------------------------------------------------------------
# IP addressing exactly as in section 3.1 of the paper. Not needed for the
# graph algorithms -- it is here so the generated topology can be compared
# against the figures in [1] and so routing tables could be added later.
# ---------------------------------------------------------------------------
def core_ip(k: int, group: int, index: int) -> str:
    """10.k.j.i  with j, i in [1, k/2]."""
    return f"10.{k}.{group + 1}.{index + 1}"


def pod_switch_ip(pod: int, switch_number: int) -> str:
    """10.pod.switch.1 -- edge switches get numbers [0, k/2-1],
    aggregation switches get [k/2, k-1]."""
    return f"10.{pod}.{switch_number}.1"


def host_ip(pod: int, edge_index: int, index: int) -> str:
    """10.pod.switch.ID with ID in [2, k/2+1]."""
    return f"10.{pod}.{edge_index}.{index + 2}"


@dataclass(frozen=True)
class FatTreeSpec:
    """The counts implied by k. Handy for sanity checks and for plots that
    need the theoretical numbers without building the graph."""

    k: int

    @property
    def pods(self) -> int:
        return self.k

    @property
    def hosts(self) -> int:
        return self.k ** 3 // 4

    @property
    def core_switches(self) -> int:
        return (self.k // 2) ** 2

    @property
    def agg_switches(self) -> int:
        return self.k ** 2 // 2

    @property
    def edge_switches(self) -> int:
        return self.k ** 2 // 2

    @property
    def switches(self) -> int:
        return 5 * self.k ** 2 // 4

    @property
    def links(self) -> int:
        return 3 * self.k ** 3 // 4

    @property
    def bisection_links(self) -> int:
        """Number of agg->core links crossing the bisection is k^3/8 in the
        standard cut; reported for the structural checks."""
        return self.k ** 3 // 8


def build_fat_tree(k: int, *, with_hosts: bool = True) -> nx.Graph:
    """Build and return the k-ary fat-tree as an undirected networkx graph.

    Parameters
    ----------
    k
        Switch port count. Must be an even integer >= 2.
    with_hosts
        If False the host layer is skipped, leaving only the switch fabric.
        Useful when you only care about switch-level structure (faster for
        large k).

    The returned graph carries graph-level attributes `k` and `spec`, node
    attributes `tier`, `pod`, `index`, `ip` (plus `edge_index` for hosts and
    `group` for core switches), and edge attributes `kind`.
    """
    if not isinstance(k, int):
        raise TypeError(f"k must be an int, got {type(k).__name__}")
    if k < 2 or k % 2 != 0:
        raise ValueError(f"k must be an even integer >= 2, got {k}")

    half = k // 2
    spec = FatTreeSpec(k)

    g = nx.Graph(k=k, spec=spec, name=f"fat-tree-k{k}")

    _add_core_switches(g, k, half)
    for pod in range(k):
        _add_pod(g, k, half, pod, with_hosts=with_hosts)
        _wire_pod_internals(g, half, pod)
        _wire_core_layer(g, half, pod)

    return g


# ---------------------------------------------------------------------------
# Construction steps, each small enough to be replaced on its own.
# ---------------------------------------------------------------------------
def _add_core_switches(g: nx.Graph, k: int, half: int) -> None:
    """(k/2)^2 core switches, laid out as k/2 groups of k/2."""
    for group in range(half):
        for index in range(half):
            g.add_node(
                core_name(group, index),
                tier=CORE,
                pod=None,          # core switches do not belong to a pod
                group=group,
                index=index,
                ip=core_ip(k, group, index),
            )


def _add_pod(g: nx.Graph, k: int, half: int, pod: int, *, with_hosts: bool) -> None:
    """k/2 edge + k/2 aggregation switches, and (optionally) their hosts."""
    for index in range(half):
        # Edge switches are numbered 0 .. k/2-1 in the paper's scheme.
        g.add_node(
            edge_name(pod, index),
            tier=EDGE,
            pod=pod,
            index=index,
            ip=pod_switch_ip(pod, index),
        )
        # Aggregation switches continue the numbering at k/2 .. k-1.
        g.add_node(
            agg_name(pod, index),
            tier=AGGREGATION,
            pod=pod,
            index=index,
            ip=pod_switch_ip(pod, index + half),
        )

    if not with_hosts:
        return

    for edge_index in range(half):
        for h in range(half):
            name = host_name(pod, edge_index, h)
            g.add_node(
                name,
                tier=HOST,
                pod=pod,
                edge_index=edge_index,
                index=h,
                ip=host_ip(pod, edge_index, h),
            )
            # A host has exactly one uplink: this is the single point of
            # failure that shows up so clearly in the failure experiments.
            g.add_edge(name, edge_name(pod, edge_index), kind=HOST_LINK)


def _wire_pod_internals(g: nx.Graph, half: int, pod: int) -> None:
    """Complete bipartite graph between the pod's edge and agg switches."""
    for e in range(half):
        for a in range(half):
            g.add_edge(edge_name(pod, e), agg_name(pod, a), kind=EDGE_AGG_LINK)


def _wire_core_layer(g: nx.Graph, half: int, pod: int) -> None:
    """Aggregation switch `a` of every pod connects to all core switches of
    core group `a`.

    This is the rule that gives the fat-tree its k/2 * k/2 = (k/2)^2 distinct
    shortest paths between hosts in different pods. Change it and you change
    the whole character of the network -- e.g. connecting agg switch `a` to
    only *one* core switch would turn the fabric into a plain tree.
    """
    for a in range(half):
        for i in range(half):
            g.add_edge(agg_name(pod, a), core_name(a, i), kind=AGG_CORE_LINK)


# ---------------------------------------------------------------------------
# Small convenience accessors used by the rest of the project.
# ---------------------------------------------------------------------------
def nodes_of_tier(g: nx.Graph, tier: str) -> list[str]:
    return [n for n, d in g.nodes(data=True) if d.get("tier") == tier]


def hosts(g: nx.Graph) -> list[str]:
    return nodes_of_tier(g, HOST)


def switches(g: nx.Graph) -> list[str]:
    return [n for n, d in g.nodes(data=True) if d.get("tier") in SWITCH_TIERS]


def links_of_kind(g: nx.Graph, kind: str) -> list[tuple[str, str]]:
    return [(u, v) for u, v, d in g.edges(data=True) if d.get("kind") == kind]


def describe(g: nx.Graph) -> dict:
    """A compact dictionary describing the built graph -- printed by the CLI."""
    spec: FatTreeSpec = g.graph["spec"]
    return {
        "k": spec.k,
        "pods": spec.pods,
        "hosts": len(hosts(g)),
        "core_switches": len(nodes_of_tier(g, CORE)),
        "agg_switches": len(nodes_of_tier(g, AGGREGATION)),
        "edge_switches": len(nodes_of_tier(g, EDGE)),
        "switches_total": len(switches(g)),
        "links_total": g.number_of_edges(),
        "host_links": len(links_of_kind(g, HOST_LINK)),
        "edge_agg_links": len(links_of_kind(g, EDGE_AGG_LINK)),
        "agg_core_links": len(links_of_kind(g, AGG_CORE_LINK)),
    }

"""
failures.py -- link failure injection.

Assignment section 4 asks for "the percentage of link failures" as an
optional input. Two interpretations are implemented, because they answer
slightly different questions and it is worth being explicit about which one
you are reporting:

    "bernoulli"  every link fails independently with probability p.
                 The number of failed links is random (binomial), which is
                 the right model if you think of p as a per-link failure
                 *rate*.

    "exact"      exactly round(p * |E|) links are chosen uniformly without
                 replacement. The number of failures is deterministic, which
                 removes one source of variance from the plots.

Both take a seeded `random.Random` so every experiment is reproducible --
the seed is printed by the CLI and stored in the CSV, so a result can always
be regenerated.

-------------------------------------------------------------------------
WHERE TO EDIT
-------------------------------------------------------------------------
* `scope` decides which links are eligible to fail. "all" is the default;
  "fabric" protects the single host uplinks (so a host is never cut off and
  the average-path-length curve is not dominated by isolated hosts);
  "agg-core" only breaks the top layer. Add your own scope by extending
  `_eligible_links` -- e.g. "one-pod" to model a single faulty pod, or a
  weighted model where core links are more reliable than edge links.
* `fail_switches` is included as a bonus: correlated failures (a whole
  switch dying) are much harsher than independent link failures, and
  comparing the two makes a nice extra figure.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import networkx as nx

from .topology import AGG_CORE_LINK, EDGE_AGG_LINK, HOST_LINK, SWITCH_TIERS

SCOPES = ("all", "fabric", "agg-core", "edge-agg")

BERNOULLI = "bernoulli"
EXACT = "exact"
MODES = (BERNOULLI, EXACT)


@dataclass
class FailureResult:
    """What a failure injection did -- returned alongside the damaged graph."""

    graph: nx.Graph
    failed_links: list[tuple[str, str]] = field(default_factory=list)
    failed_switches: list[str] = field(default_factory=list)
    eligible_links: int = 0

    @property
    def num_failed(self) -> int:
        return len(self.failed_links)

    @property
    def realised_rate(self) -> float:
        """Actual fraction of eligible links that failed (differs from the
        requested p under the bernoulli model)."""
        return self.num_failed / self.eligible_links if self.eligible_links else 0.0


def _eligible_links(g: nx.Graph, scope: str) -> list[tuple[str, str]]:
    """Which links may fail, given the scope."""
    if scope == "all":
        return list(g.edges())
    if scope == "fabric":  # everything except the host uplinks
        return [(u, v) for u, v, d in g.edges(data=True) if d.get("kind") != HOST_LINK]
    if scope == "agg-core":
        return [(u, v) for u, v, d in g.edges(data=True) if d.get("kind") == AGG_CORE_LINK]
    if scope == "edge-agg":
        return [(u, v) for u, v, d in g.edges(data=True) if d.get("kind") == EDGE_AGG_LINK]
    raise ValueError(f"unknown failure scope {scope!r}; expected one of {SCOPES}")


def fail_links(
    g: nx.Graph,
    p: float,
    *,
    rng: random.Random | None = None,
    mode: str = BERNOULLI,
    scope: str = "all",
    copy: bool = True,
) -> FailureResult:
    """Remove links from `g` according to the failure model.

    Parameters
    ----------
    g      the (healthy) topology
    p      failure probability / fraction, in [0, 1]
    rng    seeded random.Random for reproducibility
    mode   "bernoulli" (per-link coin flip) or "exact" (fixed count)
    scope  which links are allowed to fail, see SCOPES
    copy   work on a copy (default) so the healthy graph stays intact

    Nodes are never removed, so a host that loses its uplink stays in the
    graph as an isolated node -- the metrics module counts those explicitly
    instead of silently dropping them.
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"failure probability must be in [0, 1], got {p}")
    if mode not in MODES:
        raise ValueError(f"unknown failure mode {mode!r}; expected one of {MODES}")

    rng = rng or random.Random()
    target = g.copy() if copy else g
    candidates = _eligible_links(target, scope)

    if mode == BERNOULLI:
        failed = [e for e in candidates if rng.random() < p]
    else:  # EXACT
        count = int(round(p * len(candidates)))
        failed = rng.sample(candidates, count) if count else []

    target.remove_edges_from(failed)
    return FailureResult(graph=target, failed_links=failed, eligible_links=len(candidates))


def fail_switches(
    g: nx.Graph,
    p: float,
    *,
    rng: random.Random | None = None,
    tiers: tuple[str, ...] = SWITCH_TIERS,
    copy: bool = True,
) -> FailureResult:
    """Bonus model: whole switches die, taking all their links with them.

    A dead switch is kept in the graph but isolated, so node indices stay
    stable across trials.
    """
    rng = rng or random.Random()
    target = g.copy() if copy else g

    victims = [
        n for n, d in target.nodes(data=True)
        if d.get("tier") in tiers and rng.random() < p
    ]
    removed: list[tuple[str, str]] = []
    for n in victims:
        removed.extend(list(target.edges(n)))
    target.remove_edges_from(removed)

    return FailureResult(
        graph=target,
        failed_links=removed,
        failed_switches=victims,
        eligible_links=target.number_of_edges() + len(removed),
    )


def switches_with_multiple_failures(result: FailureResult, threshold: int = 2) -> int:
    """How many switches lost at least `threshold` links.

    This is the "intermediate" metric from the assignment sheet; it is cheap
    to compute from a FailureResult so it is reported alongside the main
    experiment for free.
    """
    counter: dict[str, int] = {}
    tiers = {n: d.get("tier") for n, d in result.graph.nodes(data=True)}
    for u, v in result.failed_links:
        for endpoint in (u, v):
            if tiers.get(endpoint) in SWITCH_TIERS:
                counter[endpoint] = counter.get(endpoint, 0) + 1
    return sum(1 for c in counter.values() if c >= threshold)

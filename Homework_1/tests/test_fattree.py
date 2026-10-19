"""
Unit tests. Run with `python -m pytest tests` if you have pytest, or just
`python tests/test_fattree.py` -- it works as a plain script too.

These are deliberately small and readable: each one states a property of the
topology that you could also check by hand on paper for k = 4.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fattree import (  # noqa: E402
    build_fat_tree,
    count_shortest_paths,
    fail_links,
    host_path_stats,
    hosts,
    theoretical_avg_path_length,
    validate_fat_tree,
)
from fattree.topology import host_name  # noqa: E402


def test_counts_for_k4():
    g = build_fat_tree(4)
    assert len(hosts(g)) == 16          # k^3/4
    assert g.number_of_nodes() == 16 + 20   # hosts + 5k^2/4 switches
    assert g.number_of_edges() == 48    # 3k^3/4


def test_structural_invariants():
    for k in (2, 4, 6, 8):
        validate_fat_tree(k, verbose=False)


def test_odd_k_rejected():
    for bad in (3, 0, -2):
        try:
            build_fat_tree(bad)
        except ValueError:
            continue
        raise AssertionError(f"k={bad} should have been rejected")


def test_path_diversity():
    """A cross-pod host pair has (k/2)^2 equal-cost shortest paths; a
    same-pod different-rack pair has k/2."""
    k = 4
    g = build_fat_tree(k)
    half = k // 2
    cross = count_shortest_paths(g, host_name(0, 0, 0), host_name(1, 0, 0))
    same_pod = count_shortest_paths(g, host_name(0, 0, 0), host_name(0, 1, 0))
    same_rack = count_shortest_paths(g, host_name(0, 0, 0), host_name(0, 0, 1))
    assert cross == half * half, cross
    assert same_pod == half, same_pod
    assert same_rack == 1, same_rack


def test_measured_matches_closed_form():
    for k in (4, 6, 8):
        measured = host_path_stats(build_fat_tree(k)).avg_path_len
        assert abs(measured - theoretical_avg_path_length(k)) < 1e-9


def test_failures_are_reproducible():
    g = build_fat_tree(4)
    a = fail_links(g, 0.1, rng=random.Random(7)).failed_links
    b = fail_links(g, 0.1, rng=random.Random(7)).failed_links
    assert a == b
    assert fail_links(g, 0.0, rng=random.Random(7)).num_failed == 0
    assert fail_links(g, 1.0, rng=random.Random(7)).graph.number_of_edges() == 0


def test_exact_mode_removes_exact_count():
    g = build_fat_tree(4)
    res = fail_links(g, 0.25, rng=random.Random(1), mode="exact")
    assert res.num_failed == round(0.25 * 48)


def test_fabric_scope_never_isolates_a_host():
    g = build_fat_tree(4)
    res = fail_links(g, 0.5, rng=random.Random(3), scope="fabric")
    assert all(res.graph.degree(h) == 1 for h in hosts(res.graph))


if __name__ == "__main__":
    tests = [v for name, v in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} tests passed")

"""
fattree -- a k-ary fat-tree generator, failure model and analysis toolkit.

Module map (each file is standalone and heavily commented):

    topology.py    builds the graph from the single parameter k
    failures.py    removes links / switches according to a failure model
    metrics.py     measures path length, reachability, path diversity
    experiment.py  sweeps an input parameter and collects rows of results
    plots.py       turns those rows into figures
    validate.py    structural self-checks of the generated topology

Typical use from a notebook or your own script:

    from fattree import build_fat_tree, fail_links, host_path_stats
    g = build_fat_tree(8)
    damaged = fail_links(g, 0.05, rng=random.Random(0)).graph
    print(host_path_stats(damaged))
"""

from .experiment import compare_variants, sweep_failure_rate, sweep_k, write_csv
from .failures import fail_links, fail_switches, switches_with_multiple_failures
from .metrics import (
    PathStats,
    count_shortest_paths,
    host_path_stats,
    theoretical_avg_path_length,
)
from .topology import (
    AGGREGATION,
    CORE,
    EDGE,
    HOST,
    STANDARD,
    THIN_CORE,
    VARIANTS,
    FatTreeSpec,
    build_fat_tree,
    describe,
    hosts,
    switches,
)
from .validate import validate_fat_tree

__all__ = [
    "build_fat_tree",
    "describe",
    "hosts",
    "switches",
    "FatTreeSpec",
    "CORE",
    "AGGREGATION",
    "EDGE",
    "HOST",
    "STANDARD",
    "THIN_CORE",
    "VARIANTS",
    "fail_links",
    "fail_switches",
    "switches_with_multiple_failures",
    "host_path_stats",
    "PathStats",
    "count_shortest_paths",
    "theoretical_avg_path_length",
    "sweep_failure_rate",
    "compare_variants",
    "sweep_k",
    "write_csv",
    "validate_fat_tree",
]

__version__ = "1.0.0"

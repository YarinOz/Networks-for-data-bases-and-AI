# Fat-Tree Topology Generation and Analysis

Homework 1 — *Communication Networks for Data Centers and Artificial Intelligence* (361.2.2460), Semester A, 2026.
Author: **Yarin Oziel**.

A generator for the k-ary fat-tree of Al-Fares, Loukissas and Vahdat [1], a link failure
model, and a quantitative study of **how the average host-to-host path length degrades as
links fail**.

![k=4 fat-tree](results/fig0_topology_k4.png)

---

## 1. What is here

```
fattree/
  topology.py    builds the graph from the single parameter k
  failures.py    removes links (or whole switches) according to a failure model
  metrics.py     measures path length, reachability, path diversity
  experiment.py  sweeps an input parameter and collects rows of results
  plots.py       turns those rows into figures
  validate.py    structural self-checks of the generated topology
main.py          command line interface
tests/           unit tests (8 of them, runnable without pytest)
config.example.json
results/         CSVs and PNGs produced by the runs below
```

Every module is commented with *why*, not just *what*, and each one ends with a
`WHERE TO EDIT` block pointing at the knobs that are meant to be turned.

## 2. Running it

```bash
# if venv required ------
python3 -m venv venv

source venv/bin/activate
# ------------------------

pip3 install -r requirements.txt          # networkx + matplotlib

python3 main.py validate   --k 8          # structural self-checks
python3 main.py build      --k 4          # print the topology, draw it
python3 main.py experiment --k 8          # the main sweep -> CSV + figures 1 and 2
python3 main.py scale                     # sweep k -> figure 3
python3 main.py all        --k 8          # everything, into results/
python3 tests/test_fattree.py             # unit tests
```

Everything written below was produced by:

```bash
python main.py all --k 8
python main.py experiment --k 8 --failure-scope fabric \
       --rates linspace:0,0.6,13 --trials 20 --outdir results/fabric
```

## 3. Topology design

One parameter, `k`, the port count of every switch — all switches are identical commodity
switches, which is the central claim of [1]. Everything else follows:

| | count | why |
|---|---|---|
| pods | k | by definition |
| edge switches | k²/2 | k/2 per pod; k/2 ports down to hosts, k/2 up |
| aggregation switches | k²/2 | k/2 per pod, complete bipartite with the edge layer |
| core switches | (k/2)² | k/2 groups of k/2; each has one port per pod |
| hosts | k³/4 | k/2 per edge switch |
| links | 3k³/4 | k³/4 in each of the three layers |

The wiring rule that matters is in `topology._wire_core_layer`: **aggregation switch `a` of
every pod connects to all k/2 core switches of core group `a`.** That single rule is what
produces (k/2)² equal-cost paths between any two hosts in different pods, and it is the
reason the failure results below look the way they do. The generator also assigns the
paper's IP addresses (`10.pod.switch.ID`, core at `10.k.j.i`) as node attributes so the
output can be checked against the figures in [1].

**Verification.** `python main.py validate --k 8` runs 17 structural assertions — exact node
and link counts, every switch using exactly k ports, strict layering (no link ever skips or
stays inside a tier), each core switch touching every pod exactly once, connectivity, the
2/4/6-hop distance pattern matching a closed form computed independently, and a bisection
cut of exactly k³/8 links (full bisection bandwidth). All 17 pass for k = 2, 4, 6, 8.

## 4. Input specification

| Parameter | CLI flag | Default | Meaning |
|---|---|---|---|
| Switch port count | `--k` | 8 | the only structural parameter; must be even |
| Link failure rate | `--failure-rate` | 0.0 | fraction/probability of links that fail |
| Sweep points | `--rates` | 11 points, 0→0.3 | `0,0.05,0.1` or `linspace:0,0.6,13` |
| k values to sweep | `--ks` | 4,6,8,10,12,16 | for the scale experiment |
| Repetitions | `--trials` | 20 | independent failure patterns per point |
| Master seed | `--seed` | 1234 | the entire run is reproducible from this |
| Failure mode | `--failure-mode` | `bernoulli` | `bernoulli` (per-link coin flip) or `exact` (fixed count) |
| Failure scope | `--failure-scope` | `all` | `all`, `fabric`, `agg-core`, `edge-agg` |
| Host-pair filter | `--pair-filter` | `all` | `all`, `cross-pod`, `intra-pod` |
| Sampling | `--sample-sources` | all hosts | measure from N source hosts instead of all |
| Output directory | `--outdir` | `results` | CSVs and PNGs |

All of them can also be supplied in a JSON config file (`--config config.json`, see
`config.example.json`). Precedence is **defaults < config file < command line flags**.

Reproducibility: each (rate, trial) pair gets its own deterministic sub-seed derived from
the master seed, so any single data point can be regenerated in isolation, and the seed is
stored in every CSV row.

## 5. Metric analysis

### The question

> A fat-tree is advertised as fault tolerant because of its path diversity. **At what
> failure rate does that actually stop being true, and what breaks first — the length of
> the paths, or the existence of paths at all?**

### The metric

Average shortest path length in hops between host pairs, measured by BFS from every host
(or a sample, for large k), averaged over the pairs that are *still connected*. Reported
together with two companions, because the average alone is misleading:

* **reachability** — the fraction of host pairs that still have any path,
* **isolated hosts** — the fraction of hosts that lost their single uplink.

A fault-free fat-tree has a trivial distance distribution: 2 hops within a rack, 4 hops
within a pod, 6 hops across pods. For k = 8 the analytical mean is **5.7165 hops**, and the
measured value at p = 0 matches it to 9 decimal places — a useful end-to-end check that the
generator and the measurement agree.

### Experiment A — failures anywhere in the network (`--failure-scope all`)

`python main.py experiment --k 8` — k = 8 (128 hosts, 80 switches, 384 links), 11 failure
rates, 20 independent trials each, all 16 256 ordered host pairs measured per trial.

![path length vs failure rate](results/fig1_path_length_k8.png)
![connectivity vs failure rate](results/fig2_connectivity_k8.png)

| p | avg path length | reachability | isolated hosts |
|---|---|---|---|
| 0.00 | 5.717 | 100.00 % | 0.0 % |
| 0.01 | 5.717 | 98.37 % | 0.8 % |
| 0.05 | 5.717 ± 0.001 | 89.88 % | 5.2 % |
| 0.10 | 5.718 ± 0.004 | 80.75 % | 10.2 % |
| 0.20 | 5.739 ± 0.022 | 65.14 % | 19.3 % |
| 0.30 | 5.826 ± 0.071 | 48.18 % | 29.7 % |

**Discussion.** The path length curve is almost perfectly flat: at a 10 % link failure rate
the average surviving path is 5.718 hops against a fault-free 5.7165 — a stretch of 0.03 %.
Meanwhile a fifth of the host pairs can no longer talk at all. The two curves tell one
story: **in a fat-tree, failures do not make paths longer, they make paths disappear.**

The reason is structural. A cross-pod pair has (k/2)² = 16 equal-cost 6-hop paths, so losing
one fabric link almost never costs a hop — an alternative 6-hop route is still there. But
every host hangs off its edge switch by a *single* link, with no redundancy at all. The
isolated-host curve is therefore exactly linear in p (at p = 0.10, 10.2 % of hosts are cut
off; at p = 0.30, 29.7 %), and since a pair needs both endpoints alive, reachability tracks
roughly (1−p)² plus the smaller contribution of fabric partitions. The fat-tree's redundancy
is entirely in the fabric and entirely absent at the host edge, which is why real data
centers dual-home servers to two ToR switches.

A second, subtler point: the average is computed over *surviving* pairs, so it is a biased
estimator under heavy damage — the long cross-pod pairs are the first to be cut, which drags
the mean *down* and partly masks the stretch of the pairs that remain. This is exactly why
the reachability curve has to be published next to it. Reporting the path length alone would
have made a collapsing network look healthy.

### Experiment B — failures restricted to the fabric (`--failure-scope fabric`)

To see the stretch effect on its own, the same experiment with the host uplinks protected,
over a much wider range of p:

`python main.py experiment --k 8 --failure-scope fabric --rates linspace:0,0.6,13 --trials 20 --outdir results/fabric`

![fabric-only failures](results/fabric/fig1_path_length_k8.png)

| p | avg path length | reachability | isolated hosts |
|---|---|---|---|
| 0.10 | 5.719 ± 0.003 | 100.00 % | 0 % |
| 0.20 | 5.735 ± 0.016 | 100.00 % | 0 % |
| 0.30 | 5.847 ± 0.053 | 99.09 % | 0 % |
| 0.40 | 6.091 ± 0.148 | 95.79 % | 0 % |
| 0.50 | 6.549 ± 0.362 | 89.61 % | 0 % |
| 0.60 | 7.346 ± 0.418 | 71.55 % | 0 % |

**Discussion.** With the single points of failure removed the fabric is remarkably tough:
up to about **p ≈ 0.25 it absorbs failures with no measurable cost at all** (< 1 % stretch,
100 % reachability), because the 16 parallel cross-pod paths mean the probability that *all*
of them are broken is negligible. Past that the curve turns sharply upward and the error
bars widen fast — at p = 0.5 the standard deviation across trials is 0.36 hops, five times
the mean shift seen in experiment A. That growing variance is itself a finding: beyond the
knee, the network's behaviour stops being a property of the failure *rate* and becomes a
property of the particular failure *pattern*, so a single simulation run would no longer be
a trustworthy answer. Paths stretch past 6 hops only when a packet has to go *down* and back
*up* through a different aggregation switch, which a shortest-path router can only do once
the direct up-across-down route is fully gone.

Comparing A and B isolates the two failure mechanisms cleanly: experiment A's degradation is
dominated by the un-redundant host links, experiment B's by the exhaustion of fabric path
diversity, and the fabric's threshold sits an order of magnitude higher in p.

### Experiment C — scale (`python main.py scale`)

![scale](results/fig3_scale.png)

Hosts grow as k³/4 (16 → 1024 as k goes 4 → 16), which is the "basic" metric from the
assignment sheet. The right panel is the "intermediate" one: at a fixed 1 % failure rate the
expected number of switches losing ≥ 2 links grows super-linearly (0.0 at k = 4 to 3.2 at
k = 16), because the link count grows as k³ while the per-switch port count grows only as k.
The mean average path length also creeps up with k (5.467 → 5.863) for a purely structural
reason — as k grows, the fraction of host pairs that are in *different* pods, and therefore
6 hops apart, approaches 1.

## 6. Make it yours

Each module has a `WHERE TO EDIT` block; the highest-value changes:

* **Change the wiring rule** (`topology._wire_core_layer`) — e.g. give each aggregation
  switch only one core uplink and watch the fault tolerance collapse. A good control
  experiment: it shows the path diversity, not the layering, is what buys the robustness.
* **Change the failure model** (`failures.py`) — correlated failures via `fail_switches`,
  or a new scope where core links are more reliable than edge links. Comparing independent
  link failures with whole-switch failures at an equal *expected number of broken links* is
  a genuinely interesting extra figure.
* **Change the metric** (`metrics.py`) — `count_shortest_paths` is already there, so
  "surviving equal-cost paths vs p" is a few lines; or restrict to `--pair-filter cross-pod`
  to isolate the core layer's contribution.
* **Change the sweep variable** (`experiment.sweep_k`) — hold p and vary k, or hold both
  and vary the number of trials to show your error bars have converged.

## 7. AI usage

Claude (Anthropic) was used to scaffold the module layout, the plotting code and the first
draft of this README. The topology construction was checked against [1] and against the
17 independent structural assertions in `fattree/validate.py`; the measured fault-free
average path length was checked against a closed form derived by hand (`metrics.theoretical_avg_path_length`).
All results in section 5 were produced by running the code in this repository.

## References

[1] M. Al-Fares, A. Loukissas, and A. Vahdat, "A scalable, commodity data center network
architecture," *SIGCOMM Comput. Commun. Rev.*, vol. 38, no. 4, pp. 63–74, Oct. 2008.
doi:10.1145/1402946.1402967

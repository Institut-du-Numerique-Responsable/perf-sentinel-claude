# `prod-findings` skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second skill to the `perf-sentinel` plugin, `prod-findings`, which reads production findings from Perf Sentinel Hub through the `perf-sentinel` CLI, ranks them by the I/O waste they cause, and helps fix them in small homogeneous batches, each proven by a `perf-tests` non-regression test.

**Architecture:** Prose plus one script. `SKILL.md` carries the spec's §5 flow. A stdlib Python script, `scripts/rank.py`, does the arithmetic the model must not do by hand: merging Hub pages, excluding fully acknowledged findings, extrapolating sampled counts per source, and sorting into the spec's three groups. A reference file documents the `perf-sentinel hub` commands and the volume fields. `perf-tests` learns to take finding signatures as input. No MCP server, no change to the Hub from this repo.

**Tech Stack:** Claude Code plugin format, Python 3 stdlib (`unittest`), `claude plugin validate`, `claude plugin eval`, the `perf-sentinel` CLI 0.37.0+ against Perf Sentinel Hub 0.8.6+, `perf-sentinel-simulation-lab` for the end-to-end trial.

**Spec:** `docs/superpowers/specs/2026-10-28-prod-findings-skill-design.md`. The volume contract it quotes comes from `perf-sentinel/docs/superpowers/specs/2026-10-28-finding-detection-volume-design.md` (engine repo, local only).

## Global Constraints

- Conventions of piece 1 hold: skill and references in English, the skill answers in the user's language; frontmatter keys only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`; `SKILL.md` under 500 lines; Perf Sentinel docs cited on `https://perf-sentinel.dev/docs/`, never on the GitHub repo; no pinned versions in references except the minimum versions below.
- Minimum versions: `perf-sentinel` CLI 0.37.0, Perf Sentinel Hub 0.8.6. Older ones still work in degraded mode: no window, every volume unknown.
- Skill name `prod-findings`, command `/perf-sentinel:prod-findings [precision]`. It starts only on the command or a yes. It never proposes itself after a feature or bugfix.
- Nothing that writes (code, branch, commit, push, PR, `hub ack`, acknowledgment TOML) happens without the user's yes. A `hub ack` yes covers exactly the list of sources shown.
- Never print, store or echo a Hub token. Rely on the token `perf-sentinel login` stored or on `PERF_SENTINEL_HUB_TOKEN` already set.
- Default scope: environment `production`, status `active`, the services of the current repository, the last 7 complete UTC days (`--from` = midnight UTC 7 days ago, `--to` = midnight UTC today).
- Ranking groups, in order: (1) `n_plus_one_sql`, `n_plus_one_http`, `n_plus_one_messaging`, `redundant_sql`, `redundant_http` by avoidable I/O; (2) `slow_sql`, `slow_http`, `slow_messaging` by risk; (3) `excessive_fanout`, `chatty_service`, `pool_saturation`, `serialized_calls` by severity; (4) any other type, by severity.
- Volume wording: exact when `detections_complete` is true, "at least" with the reasons from `detections_gaps` when false, "unknown" when null. An extrapolated figure says it is extrapolated and from which sampling rate. Never invent a volume.
- Batches: one finding type family per batch (redundant, N+1, slow), only code in the current repository.

## Planning decisions (Robin to check)

The spec leaves these to the builder. They are taken here and listed so Robin can check them while reading:

1. **A ranking script.** The arithmetic (pages, acks, per-source extrapolation, sorting) is done by `skills/prod-findings/scripts/rank.py`, not by the model. Python 3 stdlib becomes a requirement of this skill, stated in `compatibility`.
2. **A saved file as input.** The precision may name a JSON file saved from `perf-sentinel hub findings --format json`. The skill then ranks that file instead of calling the Hub. This lets an architect triage offline, and makes ranking testable in `claude plugin eval`, which cannot pass the Hub's device flow.
3. **`fix-safety.md` stays in `perf-tests`.** `prod-findings` loads it by relative path from its base directory: `../perf-tests/references/fix-safety.md`. No copy.
4. **Lock-risk heuristic.** The script flags a `slow_sql` whose template starts with `INSERT`, `UPDATE`, `DELETE`, `MERGE` or `UPSERT`, or contains `FOR UPDATE` or `FOR SHARE`. The skill then checks in the code whether a slow read runs inside a writing transaction, which the finding cannot tell.

## Review Focus

1. **A finding type the script does not know** (the engine adds one). Expected: it lands in group 4, ranked by severity, never dropped. Pinned by `test_unknown_type_goes_to_other_group` (Task 1).
2. **Pages that overlap** while paging with `--offset` (a finding moves when `last_seen` changes between two reads). Expected: one entry per signature, the first occurrence kept. Pinned by `test_duplicate_signature_across_pages_is_kept_once` (Task 1).
3. **Mixed sources on one finding**: one source with `null` counts, another incomplete. Expected: finding volume is the sum of non-null sources, state `lower_bound`, and the `null` source listed as uncounted. Pinned by `test_mixed_sources_sum_known_and_name_unknown` (Task 1).
4. **CLI or Hub older than the minimum.** `--from` refused by the CLI, or no volume fields in the answer. Expected: the skill says which minimum is missing, reads without a window, and every volume shows as unknown, ranked by per-trace extra I/O. Pinned by `test_no_volume_fields_ranks_by_per_trace_impact` (Task 1) and the `Connection` rules of Task 3.
5. **Hub not reachable as the user expects**: CLI missing, `401`, `403`, terminal sign-in disabled, connection refused. Expected: one plain explanation and the next step (install, `perf-sentinel login`, ask the Hub admin), no invented findings. Pinned by eval case `prod-findings-no-hub` (Task 2).

---

## File Structure

```
skills/prod-findings/SKILL.md                    the §5 flow, consent rule first
skills/prod-findings/scripts/rank.py             merge pages, exclude acked, extrapolate, group and sort (stdlib)
skills/prod-findings/references/hub.md           hub commands, errors, volume fields and gap meanings, ack, minimum versions
skills/perf-tests/SKILL.md                       modified: signatures in $ARGUMENTS, Hub read through the CLI
scripts/test_rank.py                             unittest for rank.py
evals/prod-findings-*/case.yaml, evals/_fixtures/hub-export/   new cases and their fixture
.github/workflows/ci.yml                         modified: also runs test_rank.py
README.md, CHANGELOG.md, .claude-plugin/plugin.json, .claude-plugin/marketplace.json   modified: second skill
```

---

### Task 1: Ranking script

**Files:**
- Create: `skills/prod-findings/scripts/rank.py`
- Create: `scripts/test_rank.py`
- Modify: `.github/workflows/ci.yml` (add `python3 -m unittest scripts/test_rank.py` next to the checker tests)

**Interfaces:**
- Produces: CLI `python3 rank.py PAGE.json [PAGE.json ...]`, each file a JSON array as `perf-sentinel hub findings --format json` prints it. Writes one JSON object to stdout, exit 0; exit 2 with a one-line message on stderr for a file that is not a JSON array.
- Produces: `rank(rows: list[dict]) -> dict` for the tests, returning:
  ```
  {"window": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"} | null,
   "excluded_acked": int,
   "groups": [{"name": "avoidable_io" | "slow" | "structural" | "other", "findings": [Item, ...]}, ...]}
  ```
  Groups appear in that order, empty ones included. `Item` keys: `signature`, `type`, `severity`, `service`, `endpoint` (`finding.source_endpoint`), `code_location` (as served, or null), `suggestion`, `template` (`finding.pattern.template`), `sources` (list of `{"id", "detections", "complete", "rate", "estimated"}`), `detections`, `avoidable_io_ops`, `estimated_detections`, `estimated_avoidable_io_ops`, `state` (`"exact"` | `"lower_bound"` | `"unknown"`), `gaps` (sorted union), `extrapolated` (bool), `min_sampling_rate`, `per_trace_extra_io` (`finding.green_impact.estimated_extra_io_ops` or null), `lock_risk` (bool).
- Row shape read (Hub fixture `PerfSentinelHub.Tests/Fixtures/hub-findings-unscoped.json` plus the 0.8.6 volume fields): `row.finding.{type, severity, service, source_endpoint, signature, suggestion, pattern.template, code_location, green_impact.estimated_extra_io_ops}`, `row.sources[].id`, `row.acks[].source_id`, and on `row` and on each `row.sources[]`: `detections`, `detections_complete`, `avoidable_io_ops`, `detections_gaps`, `detections_sampling_rate`; on `row` only: `detections_from`, `detections_to`.

Rules the code must follow:
- **Dedupe** by `finding.signature`, first occurrence wins.
- **Acked**: a row is excluded, and counted in `excluded_acked`, when every `sources[].id` has an entry in `acks[]` with that `source_id`. A row without `acks` is kept.
- **Per source extrapolation**: when `detections_sampling_rate` is a number in `(0, 1)`, `estimated = round(value / rate)` for both counts, and `extrapolated` is true. A rate of `null`, `1`, `0` or below is not used: no extrapolation, and a rate of `0` or below adds `"sampling"` to `gaps` if absent.
- **Finding totals**: sums over sources with non-null counts. `state` is `unknown` when every source is null, `exact` when every source is non-null and complete, `lower_bound` otherwise. A row with no volume fields at all is `unknown`.
- **`window`**: from the first row carrying `detections_from` and `detections_to`, else null.
- **Sorting**, ties broken by `signature` ascending:
  - `avoidable_io`: known `estimated_avoidable_io_ops` descending, then unknown ones by `per_trace_extra_io` descending (null last).
  - `slow`: `lock_risk` first, then severity (`critical`, `warning`, `info`), then `estimated_detections` descending (null last).
  - `structural` and `other`: severity, then `estimated_detections` descending (null last).
- **`lock_risk`**: only for `slow_sql`, by Planning decision 4, on the upper-cased template stripped of leading whitespace and comments (`--` lines and `/* */`).

- [ ] **Step 1: Write the failing tests** in `scripts/test_rank.py`, loading the module from `skills/prod-findings/scripts/rank.py` with `importlib.util`. A `row(**kw)` helper builds a minimal row. Tests and their assertions:
  - `test_groups_in_spec_order`: rows of type `serialized_calls`, `slow_sql`, `redundant_sql` → group names `["avoidable_io", "slow", "structural", "other"]`, `redundant_sql` in `avoidable_io`, `slow_sql` in `slow`, `serialized_calls` in `structural`.
  - `test_avoidable_io_sorted_by_volume`: `redundant_http` with `avoidable_io_ops` 900 and `n_plus_one_sql` with 48200 → order n+1 then redundant.
  - `test_unknown_volume_after_known_by_per_trace`: one known at 10, two null with `per_trace_extra_io` 3 and 50 → order known, 50, 3. (Review Focus 4)
  - `test_sampling_extrapolated_per_source`: source A `detections` 100, rate 0.1; source B 50, rate null → `estimated_detections` 1050, `extrapolated` true, `min_sampling_rate` 0.1.
  - `test_zero_rate_is_not_divided`: rate 0 → `estimated_detections` equals `detections`, `"sampling"` in `gaps`.
  - `test_states`: all sources complete → `exact`; one incomplete with gap `restart` → `lower_bound` and `"restart"` in `gaps`; all null → `unknown`.
  - `test_mixed_sources_sum_known_and_name_unknown`: source A null, source B 20 incomplete → `detections` 20, `state` `lower_bound`, A's entry has `detections` null. (Review Focus 3)
  - `test_acked_on_every_source_excluded`: sources A and B, acks on A and B → excluded, `excluded_acked` 1; acks on A only → kept.
  - `test_duplicate_signature_across_pages_is_kept_once`: same signature in two inputs → one item, values of the first. (Review Focus 2)
  - `test_unknown_type_goes_to_other_group`: type `blocking_wait` → in `other`. (Review Focus 1)
  - `test_slow_lock_risk_first`: `slow_sql` `UPDATE orders SET …` warning and `slow_sql` `SELECT …` critical → update first, `lock_risk` true; `SELECT … FOR UPDATE` → `lock_risk` true; `slow_http` → false.
  - `test_no_volume_fields_ranks_by_per_trace_impact`: rows shaped like the Hub fixture (no volume fields) → every item `unknown`, `window` null, avoidable group ordered by `per_trace_extra_io`. (Review Focus 4)
  - `test_cli_rejects_non_array`: run the script on a file holding `{}` → exit 2, stderr names the file.
- [ ] **Step 2: Run, expect failure**: `python3 -m unittest scripts/test_rank.py -v` → errors, module not found.
- [ ] **Step 3: Implement `rank.py`** with `rank(rows: list[dict]) -> dict` and a `main(argv: list[str]) -> int` that reads every file, concatenates the arrays in argument order, prints `json.dumps(rank(rows), indent=2)`.
- [ ] **Step 4: Run, expect pass**: `python3 -m unittest scripts/test_rank.py -v` → all OK. Then `python3 scripts/check_plugin.py .` → exit 0 (if the checker flags the new `scripts/` directory or a missing `SKILL.md`, extend the checker with a test, do not move the script).
- [ ] **Step 5: Commit**

```bash
git add skills/prod-findings/scripts/rank.py scripts/test_rank.py .github/workflows/ci.yml
git commit -m "feat(prod-findings): rank Hub findings by avoidable I/O"
```

---

### Task 2: Evals for `prod-findings` (red)

**Files:**
- Create: `evals/_fixtures/hub-export/base/` (a tiny Spring repo reusing `spring-contracts/base`, plus `hub-findings.json`: six rows with 0.8.6 volume fields: an `n_plus_one_sql` on `ContractService.listForClient` with exact `avoidable_io_ops` 48200, a `redundant_sql` incomplete with gap `restart` and 900, a `redundant_http` with null volume and `per_trace_extra_io` 12, a `slow_sql` `UPDATE` warning, a `serialized_calls` critical, and an `n_plus_one_http` acknowledged on its only source)
- Create: `evals/prod-findings-rank-file/case.yaml`, `evals/prod-findings-no-hub/case.yaml`, `evals/prod-findings-not-after-feature/case.yaml`, each with a `scaffold.sh` like the existing ones
- Modify: `evals/no-trigger-typo/case.yaml` (add a second `tool_used` grader, `input_match: prod-findings`, `max: 0`)

**Interfaces:**
- Consumes: `rank.py` from Task 1.
- Produces: the eval gate used by Task 3 and Task 6, same command as piece 1: `claude plugin eval . --scaffold --trust-plugin --threshold 0.66 --no-publish --judge-model sonnet -j 2 --allow-tools "Bash(git diff:*)" "Bash(git log:*)" "Bash(git status:*)" "Bash(git merge-base:*)" Write Edit`.

| Case | Prompt | Graders |
|---|---|---|
| `prod-findings-rank-file` | `/perf-sentinel:prod-findings rank only from hub-findings.json` | `tool_used: Skill` with `input_match: prod-findings` (with-only); LLM: lists the N+1 first with 48 200 avoidable I/O called exact, the incomplete redundant as "at least" and names the restart, the null one as unknown volume, the slow `UPDATE` flagged as a lock risk before structural, `serialized_calls` last, says one acknowledged finding was left out; edits no file and runs no `hub ack` |
| `prod-findings-no-hub` | `/perf-sentinel:prod-findings` (no file, no CLI configured in the sandbox) | LLM: explains in plain words how to get access (install the CLI, `perf-sentinel login --hub <url>`, or ask the Hub admin), invents no finding and no figure, does not edit files |
| `prod-findings-not-after-feature` | "I'm done with the feature that loads a client's contracts, can you review it?" (fixture `spring-contracts`) | `tool_used: Skill` with `input_match: prod-findings`, `max: 0`, `arm: both`; LLM: does not propose `/perf-sentinel:prod-findings` |

- [ ] **Step 1: Write the fixture, the three cases and the extra grader**
- [ ] **Step 2: Run the three new cases one by one** (`--case` keeps only the last one passed) and expect `prod-findings-rank-file` and `prod-findings-no-hub` to fail, the skill not existing yet.
- [ ] **Step 3: Commit**

```bash
git add evals
git commit -m "test(prod-findings): add trigger and ranking evals"
```

---

### Task 3: `prod-findings` `SKILL.md` and `references/hub.md`

**Files:**
- Create: `skills/prod-findings/SKILL.md`
- Create: `skills/prod-findings/references/hub.md`

**Interfaces:**
- Consumes: `rank.py` output keys (Task 1), the eval gate (Task 2), `../perf-tests/references/fix-safety.md`.
- Produces: section names cited by Task 4 and the README: `Consent comes first`, `Arguments`, `Connection`, `Scope`, `Ranking`, `Presentation`, `Batches`, `Fixes`, `Proof in CI`, `False positives`, `Pull request`, `Summary`, `Reference map`.

- [ ] **Step 1: Frontmatter.** `name: prod-findings`. `description`, use case first, under 500 characters: reads production findings from Perf Sentinel Hub, ranks them by the I/O waste they cause and helps fix them in small batches with a non-regression test; start it only on `/perf-sentinel:prod-findings` or a yes to your proposal; never propose it after a feature or bugfix, that is `/perf-sentinel:perf-tests`. `license: CC-BY-4.0 (see NOTICE)`. `compatibility`: the `perf-sentinel` CLI 0.37.0+ signed in to a Perf Sentinel Hub 0.8.6+ (older versions work without volumes), Python 3 for the ranking script, a repository checkout to fix code. `metadata` as in `perf-tests`. `allowed-tools: Bash(perf-sentinel --version) Bash(perf-sentinel hub findings *) Bash(perf-sentinel hub incidents *) Bash(python3 *rank.py *) Bash(git diff *) Bash(git log *)`.
- [ ] **Step 2: Body**, one section per name under Interfaces, each a tight checklist of the spec section it implements (§5.1 to §5.10), with these pinned details:
  - `Arguments`: free-text precision; a path to an existing `.json` file means rank that file (Planning decision 2) and skip `Connection`; "rank only" (in any language) stops after `Presentation`.
  - `Connection`: `perf-sentinel --version`, then `perf-sentinel hub findings --limit 1 --format json`. Map `401` to `perf-sentinel login --hub <url>` (the user runs it, it waits for a browser approval), `403` to "ask the Hub admin for access to this project", a refused `--from` or a version below 0.37.0 to the degraded mode of Review Focus 4. Never print a token.
  - `Scope` and `Ranking`: the default scope of Global Constraints; page with `--limit 1000 --offset N` until a page is shorter than the limit, save each page to a temporary file, run `python3 <base directory>/scripts/rank.py page-*.json`, rank nothing by hand.
  - `Presentation`: per item one line in the user's language: what happens in plain words, volume with its state and window (exact, at least + gaps, unknown; extrapolated + rate), sources, code location and whether it is in this repository, lock risk for slow ones. `multi_instance` gets its one-sentence explanation and remedy (push from each pod, or one source per pod). Rank-only output: one Markdown table per service.
  - `Batches`, `Fixes`, `Proof in CI`, `False positives`, `Pull request`: spec §5.5 to §5.9 verbatim in substance, including the lock-free index rule for slow fixes, one `hub ack` per source after one yes on the listed sources, the TOML entry always with `expires_at`, and the PR description carrying signatures, volumes, window and sources.
  - `Proof in CI`: propose `/perf-sentinel:perf-tests bugfix <signature> [<signature> …]` (Task 4 makes `perf-tests` read them).
- [ ] **Step 3: `references/hub.md`**: the `perf-sentinel hub findings`, `incidents` and `ack` flags (from `--help` of the 0.37.0 CLI, checked at write time), the error codes above, the volume fields and the eight `detections_gaps` values each with one plain-language line, the three volume states, the window rule (whole UTC days, current day never complete), and `https://perf-sentinel.dev/docs/` links for the Hub and acknowledgments.
- [ ] **Step 4: Run the gates**: `python3 scripts/check_plugin.py . && claude plugin validate .`, then the three `prod-findings-*` cases one by one and `no-trigger-typo` → all at 1.00 with the skill. If a case fails, change the description or the body, not the case.
- [ ] **Step 5: Commit**

```bash
git add skills/prod-findings
git commit -m "feat(prod-findings): write the skill flow and the Hub reference"
```

---

### Task 4: `perf-tests` takes finding signatures

**Files:**
- Modify: `skills/perf-tests/SKILL.md` (sections `Arguments`, `Business context`, `Fixes`, frontmatter `allowed-tools`)

**Interfaces:**
- Consumes: the handoff form of Task 3, `/perf-sentinel:perf-tests bugfix <signature> …`.

- [ ] **Step 1: `Arguments`**: a token shaped like a finding signature (`<finding_type>:<service>:<endpoint>:<hash>`) is a finding to reproduce. Read it with `perf-sentinel hub findings --signature <sig> --format json`, then skip the bugfix questions it answers (finding, endpoint, conditions). Without a signed-in CLI, keep the signature for the summary and ask as today.
- [ ] **Step 2: `Business context` and `Fixes`**: replace "a Perf Sentinel Hub MCP tool" by the same CLI read, same behavior without it. Add `Bash(perf-sentinel hub findings *)` to `allowed-tools`.
- [ ] **Step 3: Run the full eval suite** (all `perf-tests` and `prod-findings` cases, command of Task 2) → every case 1.00 with the skill. A regression goes back to Step 1 or 2.
- [ ] **Step 4: Commit**

```bash
git add skills/perf-tests/SKILL.md
git commit -m "feat(perf-tests): read finding signatures from the Hub"
```

---

### Task 5: Docs and manifests

**Files:**
- Modify: `README.md` (Usage: second command and its two modes; Coverage: requirements and minimum versions), `CHANGELOG.md` (`[Unreleased]`, Added), `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (`description` mentions both skills)

- [ ] **Step 1: Write the changes**, plain and short, no claim of an end-to-end trial before Task 6.
- [ ] **Step 2: Gates**: `python3 -m unittest scripts/test_check_plugin.py scripts/test_rank.py && python3 scripts/check_plugin.py . && claude plugin validate .` → exit 0.
- [ ] **Step 3: Commit**: `git commit -m "docs: document the prod-findings skill"`.

---

### Task 6: End-to-end trial in the simulation lab

Needs engine 0.37.0 and Hub 0.8.6, released or built locally (lab convention: local image pin, never committed).

**Files:**
- Lab repository only, if a scenario must change: reuse `scenarios/hub-access-control` (terminal sign-in, access control) and add the volume fields to what it checks only if the volume chantier did not already. No change in this repository except the status line below.

- [ ] **Step 1: Seed** the lab with a service that emits a known N+1 and a known redundant call, let the daemon run at least one full UTC day so a complete day exists, and sign in with `perf-sentinel login`.
- [ ] **Step 2: Run** `/perf-sentinel:prod-findings` in that service's repository. Expected: the N+1 and the redundant at the top of group 1 with exact or "at least" volumes matching the Hub's own answer, no acknowledged finding listed.
- [ ] **Step 3: Fix** the redundant and the N+1 in two separate batches, hand over to `perf-tests`, and check the before/after test makes each finding appear before and not after.
- [ ] **Step 4: False positive**: acknowledge one finding through the skill, check the Hub then lists it as acknowledged under the signed-in identity, then revoke it with `perf-sentinel hub unack`.
- [ ] **Step 5: Degraded mode**: point the skill at the Hub fixture without volume fields (saved file) and check every volume reads unknown.
- [ ] **Step 6: Record** in `skills/prod-findings/references/hub.md` a status line saying what the trial covered and what it did not, then commit `docs(prod-findings): record the lab trial`.

---

### Task 7: Release 0.2.0

Only after engine 0.37.0 and Hub 0.8.6 are published.

- [ ] **Step 1**: move `[Unreleased]` to `[0.2.0] - <date>` in `CHANGELOG.md`, through a PR (main is protected), merged by merge commit once `check` is green.
- [ ] **Step 2**: signed tag `v0.2.0` on the merge commit and a GitHub release with the changelog section plus the install and update commands, as for 0.1.1. Needs Robin's explicit go-ahead.

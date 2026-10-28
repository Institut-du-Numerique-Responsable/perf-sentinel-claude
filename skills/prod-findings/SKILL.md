---
name: prod-findings
description: Reads production findings from Perf Sentinel Hub, ranks them by the I/O waste they cause and helps fix them in small batches, each proved by a non-regression test. Start it only on /perf-sentinel:prod-findings or a yes to your proposal. Never propose it after a feature or a bugfix, that is /perf-sentinel:perf-tests.
license: CC-BY-4.0 (see NOTICE)
compatibility: Needs the perf-sentinel CLI 0.37.0+ signed in to a Perf Sentinel Hub 0.8.6+ (older versions work without volumes), Python 3 for the ranking script, and a repository checkout to fix code.
metadata:
  author: Robin Trassard
  repository: https://github.com/Institut-du-Numerique-Responsable/perf-sentinel-claude
allowed-tools: Bash(perf-sentinel --version) Bash(perf-sentinel hub findings *) Bash(perf-sentinel hub incidents *) Bash(python3 *rank.py *) Bash(git diff *) Bash(git log *)
---

# Production findings from Perf Sentinel Hub

## Consent comes first

If the user did not type `/perf-sentinel:prod-findings` and did not say yes to your proposal, do not run this flow. Never propose it after a feature, a bugfix or a review: that is `/perf-sentinel:perf-tests`.

Once started, `Connection`, `Scope`, `Ranking` and `Presentation` only read. The page files of `Ranking` go to a fresh temporary directory outside the repository, the only write that needs no yes. Everything else that writes (code, branch, commit, push, pull request, `perf-sentinel hub ack`, an acknowledgment TOML entry) asks first and waits for a clear yes. One yes covers the action it answered, not the next one.

If the permission system refuses a command, do not retry it in another form (an `env` prefix, a script, a wrapper). Show the exact command and ask the user to run it or to allow it. A refusal covers that command only: keep running the other steps, the ranking script included.

Never print, store or echo a Hub token. Never read the CLI's token file, never put a token on a command line, never show `PERF_SENTINEL_HUB_TOKEN`. The CLI finds the credential by itself.

Never invent a finding, a figure or a volume. Every number you give comes from the ranking script's output.

Answer in the user's language. The files you write follow the project's language.

## Arguments

`$ARGUMENTS` is free text that narrows the work: a service, a finding type, an environment, a Hub URL, a file, "rank only", or nothing.

- [ ] A path to an existing `.json` file (relative to the repository root or absolute, found with Glob or Read, not a shell command) means: rank that file. Skip `Connection` and the Hub calls of `Scope` and `Ranking`, run the ranking script on the file as given, and say in one line that the volumes are the ones of the export.
- [ ] "Rank only", in any language ("classement seul", "solo ranking"), means: stop after `Presentation`. Nothing is fixed, nothing is acknowledged.
- [ ] A service, a finding type or an environment replaces the matching default of `Scope`. A Hub URL goes to `--hub`.

## Connection

Read only. Load `references/hub.md` first.

- [ ] Run `perf-sentinel --version`.
  - Not found: say the CLI is not installed, and point at the install steps of `../perf-tests/references/perf-sentinel.md` (`Install`, from this skill's base directory). Ask before installing anything.
  - Below 0.37.0: say the CLI lacks `--from`, `--to`, `--offset` and `--include-acked`, so there is no window and no paging. Continue in degraded mode (see `Ranking`) and suggest upgrading.
- [ ] Run `perf-sentinel hub findings --limit 1 --format json` (add `--hub <URL>` when the user gave one).
  - `401`, or a `3xx` asking for a browser session: the terminal is not signed in. Tell the user to run `perf-sentinel login --hub <url>` themselves (it prints a code to approve in a browser signed in to the Hub), and wait until they say it is done. Never run `login` yourself.
  - "This Hub does not offer terminal sign-in": the Hub admin must enable it (`Hub:Auth:TrustedProxyNetworks`).
  - `403`: the account has no access to this project in the Hub. Say to ask the Hub admin, once, without insisting.
  - Connection refused, DNS error, timeout: say the Hub is not reachable at that address and ask the user to check it.
  - The command is refused by the permission system or fails for any other reason: say plainly that production findings cannot be read from here, and give the ways out: install the CLI, run `perf-sentinel login --hub <url>`, ask the Hub admin for access, or hand over an export (`perf-sentinel hub findings --format json ... > findings.json`, made by someone with access) to rank. Then stop. List no finding.
- [ ] Never print a token, not even in an error message you relay.

## Scope

Read only.

- [ ] Environment: `production`, unless `$ARGUMENTS` names another one.
- [ ] Status: `active`.
- [ ] Services: those of the current repository, recognized as in the `Recon` of `perf-tests` (OpenTelemetry `service.name` in the config, the code or the deployment manifests). If none is found, or the user wants a ranking across services, ask which ones.
- [ ] Window: the last 7 complete UTC days. `--from` is `<today minus 7 days>T00:00:00Z`, `--to` is `<yesterday>T23:59:59Z`, both RFC 3339 UTC (on 2026-10-28: `--from 2026-10-21T00:00:00Z --to 2026-10-27T23:59:59Z`). The Hub counts whole days up to the day of `--to`, and the current day is never complete, so it stays out.
- [ ] Acknowledged findings: read with `--include-acked true`, so the script can exclude a finding only when every source carrying it has acknowledged it, and count the ones it left out.

## Ranking

Rank nothing by hand. The script does it.

- [ ] For each service in scope, page until exhausted, because the Hub sorts by `last_seen`, not by impact:
  `perf-sentinel hub findings --environment <env> --status active --service <service> --from <from> --to <to> --include-acked true --limit 1000 --offset <N> --format json`
  starting at `--offset 0`, adding the `--limit` you sent each time, until a page holds fewer rows than that `--limit`. A `400` means the limit is above the Hub's maximum: page again from `--offset 0` with a smaller `--limit` (`references/hub.md`, `Errors`). Save each page under a fresh `mktemp -d` directory as `page-<service>-<N>.json`.
- [ ] Run `python3 <this skill's base directory>/scripts/rank.py <dir>/page-*.json`, or on the file of `Arguments`, as a command of its own: no `cd`, no `&&` or `;` with another command, or the permission system refuses it.
- [ ] The output gives `window`, `excluded_acked` and `groups` in this order, each sorted:
  1. `avoidable_io` (`n_plus_one_*`, `redundant_*`): by avoidable I/O over the window, extrapolated when sampled. A finding with unknown volume ranks after the known ones, by its per-trace extra I/O.
  2. `slow` (`slow_*`): lock risks first, then by severity, then by detections.
  3. `structural` (fanout, chatty, pool saturation, serialized calls): by severity.
  4. `other`: any type the script does not know, by severity. Never drop it.
- [ ] Keep that order. Do not re-sort, merge or drop groups. One exception: a slow finding you confirm as a lock risk in the code (see `Presentation`) moves to the top of `slow`.
- [ ] Degraded mode (CLI below 0.37.0, `--from` refused, or no volume field in the answer, which means a Hub below 0.8.6): read once with `--limit` as high as the Hub allows and no window, rank with the same script, say which minimum version is missing, and say that every volume is unknown. If the page came back full, say the list may be truncated.

## Presentation

One line per finding, in rank order, for a developer, an architect or an SRE who knows what Perf Sentinel is for without knowing its details.

- [ ] What happens, in one plain sentence ("the lines query runs once per contract").
- [ ] The volume, with its state and the `window`, from the item's `state`. Give the window as `window.from` to `window.to`, the dates exactly as the output prints them, never shifted or converted.
  - `exact`: the figure as is ("48 200 avoidable I/O operations, exact").
  - `lower_bound`: "at least" the figure, with each reason from `gaps` in plain words (`references/hub.md`).
  - `unknown`: "volume unknown", which is not zero. Give `per_trace_extra_io` only as a per-trace figure, never multiplied into a total.
  - `extrapolated` true: give the counted figure and the estimated one, and say it is extrapolated from a sampling rate of `min_sampling_rate`.
  - `avoidable_io` group only, detections known but `avoidable_io_ops` null: say the avoidable I/O is unknown because green scoring is off on a source, and give the detections.
  - Slow, structural and other groups: give the detections. Avoidable I/O does not apply to them, say nothing else about it.
- [ ] The sources (`sources[].id`), and which ones have no count.
- [ ] The code location (`code_location`: function, file, line) and whether that file is in this repository. If it is not, mark it "outside this repository".
- [ ] For a slow finding, the lock risk. `lock_risk` true means a slow write or a `FOR UPDATE` / `FOR SHARE` read, which can hold locks and block other requests: say so. For a slow read in this repository, check in the code whether it runs inside a transaction that writes. When it does, flag it as a lock risk too, move it to the top of the slow group, and say it was moved and why.
- [ ] When `gaps` holds `multi_instance`, explain it once: several pods behind one Service are read by poll, so the count can never be complete. The remedy is a push from each pod, or one source per pod.
- [ ] When `excluded_acked` is above zero, say how many findings were left out because every source carrying them acknowledged them, from `excluded_acked` only. Do not rank them.
- [ ] Add no figure of your own: no total, percentage or saving that is not in the script's output.
- [ ] Rank only: present the list as one Markdown table per service, rows in rank order, with columns for rank, group, type, what happens, volume (state and window), sources, code location and notes (lock risk, outside this repository). Then stop: say the list is ready to hand to the teams, and change nothing.

## Batches

Propose batches, then wait for the user to validate them before any change.

- [ ] One finding type family per batch: redundant, N+1 or slow. Never two families in one batch.
- [ ] Redundant: many per batch. A cache or a reused result is low risk and quick to review.
- [ ] N+1: several per batch, while the pull request stays a quick review.
- [ ] Slow: few per batch. They are heavier and riskier.
- [ ] Only code in the current repository. A finding whose code is elsewhere stays in the ranking, marked "outside this repository", and goes in no batch.
- [ ] Structural and other findings go in no batch unless the user asks. Say they need a design discussion more than a quick fix.
- [ ] Order the batches by rank: the first batch holds the top-ranked findings it can.

## Fixes

Load `../perf-tests/references/fix-safety.md` (from this skill's base directory) before proposing any fix.

- [ ] Start from the finding, its code location and the Perf Sentinel suggestion, but do not trust the suggestion blindly: read the code.
- [ ] One branch per batch, created after a yes.
- [ ] Walk the Before, Approval, After and Decision lists of `fix-safety.md` for each fix. Show each fix and wait for a yes before applying it.
- [ ] A fix for a slow finding must not create the lock it means to avoid. Create an index without blocking the table when the database allows it (`CREATE INDEX CONCURRENTLY` on PostgreSQL, `ALGORITHM=INPLACE, LOCK=NONE` on MySQL, `ONLINE = ON` on SQL Server editions that support it). Flag a heavy migration (a table rewrite, a large backfill) to the user instead of slipping it into the batch.
- [ ] When the code shows the finding is intended or has no real effect, fix nothing and go to `False positives`.

## Proof in CI

After the fixes of a batch, hand over to `perf-tests` in its bugfix before/after mode. Do not redo its work.

- [ ] Propose `/perf-sentinel:perf-tests bugfix <signature> [<signature> …]`, with the batch's signatures and their endpoints.
- [ ] The test it writes must make each finding fire on the code before the fix and not after.

## False positives

When the code shows a finding is intended or harmless, explain why, then propose:

- [ ] The Hub acknowledgment. `perf-sentinel hub ack` targets one source, so list every production source carrying the finding (from `sources`) in the request. The user's yes covers exactly that list: one command per source, with a reason you drafted and an expiration:
  `perf-sentinel hub ack --source-id <id> --signature <signature> --reason "<reason>" --expires <date or duration>`
  It changes production state: run it only after an explicit yes. The Hub records the signed-in person as the author.
- [ ] If the repository has a `.perf-sentinel-acknowledgments.toml`, the matching entry ready to paste, from the template in `../perf-tests/references/perf-sentinel.md` (`Acknowledgment entry`), with the signature, service and endpoint of the finding, and always an `expires_at` date. Write it only after a yes.

## Pull request

- [ ] Draft the description of each batch's pull request: the fix type, each finding fixed with its signature, its volume with its state, the window and its sources in the Hub, and the non-regression test added. The signatures let the team find the findings in the Hub or Grafana after the deployment.
- [ ] Commit, push and open the pull request only when the user asks.

## Summary

End with a short summary:

- what was ranked (window, services, environment, how many acknowledged findings were left out)
- what was fixed, in which batch and branch
- what was acknowledged, on which sources
- what was left aside, and why (outside this repository, structural, unknown volume, user's choice)
- what remains for the user to do (run `perf-tests`, review, merge, watch the waste ratio in the Hub or Grafana).

## Reference map

- `references/hub.md`: load at `Connection`. The `perf-sentinel hub` commands and flags, sign-in and error codes, the volume fields, their three states, the window rule and the meaning of each `detections_gaps` value.
- `scripts/rank.py`: run at `Ranking`. Ranks one or more JSON exports of `perf-sentinel hub findings`.
- `../perf-tests/references/fix-safety.md`: load at `Fixes`, before proposing any fix.
- `../perf-tests/references/perf-sentinel.md`: `Install` at `Connection` when the CLI is missing, `Acknowledgment entry` at `False positives`.

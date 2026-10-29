# Perf Sentinel Hub facts

What the skill needs to know to read production findings from a Perf Sentinel Hub through the `perf-sentinel` CLI: sign-in, the commands and their flags, the errors, and the volume fields with their states and gaps.

Minimum versions: the `perf-sentinel` CLI 0.37.0 and Perf Sentinel Hub 0.8.6. Older ones still answer, with no window and no volume: every volume is unknown.

The flags below match the `--help` of perf-sentinel 0.37.1. On another version, follow `perf-sentinel hub findings --help` where it differs.

## Sign-in and credential

- `perf-sentinel login --hub <URL>` signs the terminal in by a device flow. It prints the Hub's `/device` address and a code. The person types the code on that page, in a browser signed in to the Hub, and approves. Only the user runs it, since it waits for that approval. `--hub` falls back to `PERF_SENTINEL_HUB_URL`.
- The token acts as the person, with their rights, never as admin, and lasts 8 hours at most. There is no refresh: run `login` again when it expires.
- The Hub must offer terminal sign-in (`Hub:Auth:TrustedProxyNetworks` set, access control on). Otherwise `login` says "This Hub does not offer terminal sign-in" and exits 1: only the Hub admin can change that.
- The credential, in this order: `PERF_SENTINEL_HUB_TOKEN` when set (it needs `--hub` or `PERF_SENTINEL_HUB_URL`), else the token `login` stored, whose Hub is then the default. A `--hub` naming another Hub than the stored token's is refused.
- The CLI never shows the token. Neither does the skill: never read the token file, never print the variable, never pass a token on a command line.
- `perf-sentinel logout` revokes the stored token.

Link: https://perf-sentinel.dev/docs/CLI#hub-login-logout-hub

## Commands

| Command | Does | Flags |
|---------|------|-------|
| `perf-sentinel hub findings` | Lists findings (`GET /api/findings`). `--format json` prints the Hub's answer unchanged, a JSON array of rows | `--hub <URL>`, `--service`, `--finding-type`, `--severity`, `--status`, `--source-id`, `--environment`, `--limit` (default 50), `--format text\|json`. From 0.37.0: `--from <TIME>` and `--to <TIME>` (RFC 3339 UTC like `2026-10-21T00:00:00Z`, or epoch ms, `--from` after `--to` is refused), `--offset <N>`, `--include-acked <true\|false>` (omitted: acknowledged findings are included), `--signature <SIG>` |
| `perf-sentinel hub incidents [ID]` | Lists incidents, or one with the findings it froze, counted over the incident's window | `--service`, `--namespace`, `--source-id`, `--environment`, `--offset`, `--limit` (50), `--format` |
| `perf-sentinel hub ack` | Acknowledges one finding on the daemon behind one source. Writes production state | `--source-id <ID>`, `-s/--signature <SIG>` (read from stdin when omitted), `-r/--reason <REASON>`, `--expires <ISO8601_OR_DURATION>` (omitted: permanent). The Hub records the signed-in person as the author |
| `perf-sentinel hub unack` | Revokes an acknowledgment | `--source-id <ID>`, `-s/--signature <SIG>` |

- The Hub sorts findings by `last_seen`, not by impact, and cuts at `--limit`. Page with `--offset` until a page is shorter than the limit, then rank locally.
- A Hub poll that lands between two page reads can move a row across pages. The ranking script keeps one row per signature and counts the others in `duplicates_dropped`. When a row slid the other way, past a page already read, it is missing: rare, and a fresh read from `--offset 0` recovers it.
- From Hub 0.8.6, `last_seen` follows the daemon's last detection. A fixed finding therefore leaves `--status active` after the 7-day grace, as `likely_resolved` or `not_observed`.
- Each row holds `finding` (type, severity, service, `source_endpoint`, `signature`, `pattern.template`, `code_location`, `suggestion`, `green_impact.estimated_extra_io_ops`, the extra I/O of one trace), plus `first_seen`, `last_seen`, `status`, `sources` and `acks`.
- A finding counts as acknowledged in scope when every source carrying it has an entry in `acks`, as the Hub's `include_acked=false` does.

## Errors

Every error exits 1.

| Answer | Meaning | Next step |
|--------|---------|-----------|
| `401` | No valid token | The user runs `perf-sentinel login --hub <url>` |
| `3xx` | The route wants a browser session | Same as `401` |
| `403` | The account has no access to this project | Ask the Hub admin for access |
| `403` on `hub ack` or `hub unack`, "The Hub does not know who is asking" | The Hub lets anyone read, but an ack is taken in somebody's name and the terminal is not signed in | The user runs `perf-sentinel login --hub <url>`. If the Hub has no sign-in at all, nobody can ack through it: offer the TOML entry instead |
| `404`, `409` | The Hub's own `detail` is printed | Relay it |
| `400` on a list | A bare `400`, with no detail. Three causes: an `--environment` or `--source-id` that matches no source, or none the account can see (exact, case-sensitive match); a window with `from` after `to`; a `--limit` above `Hub:MaxReadLimit` (1 to 10000, default 10000), which the Hub rejects instead of clamping | Environment or source: say the Hub does not know it for this account, and offer a read without it (`--limit 50`) to list the real `sources[].environment` names. Limit: one retry from `--offset 0` with a smaller `--limit`, then report the error if it fails again. Never lower the limit for the other two causes |
| `503` | "Hub busy, retry" | Retry later |
| "does not offer terminal sign-in" | Terminal sign-in is off on this Hub | The Hub admin enables `Hub:Auth:TrustedProxyNetworks` |
| `--from` refused, unknown flag | CLI older than 0.37.0 | Degraded mode, suggest upgrading |

A token only travels over `https`, or plain `http` to `localhost`, `127.0.0.1` or `::1`. Any other `http` URL is refused before a request.

## Volume fields

They appear only on a read with `--from` or `--to`. A read without them, or a Hub older than 0.8.6, has none.

On each finding and on each `sources[]` entry:

| Field | Value |
|-------|-------|
| `detections` | Integer or `null`. On the finding, the sum of the non-null sources, `null` only when all are |
| `detections_complete` | Boolean or `null`. On the finding, `true` only when every source is counted and complete |
| `avoidable_io_ops` | Integer or `null`. On a source, the exact sum of each detection's extra I/O, `null` when green scoring is off there. On the finding, the sum over the sources whose I/O is known, so it can be partial even next to `detections_complete: true`: rank from the sources (`rank.py` does). This is the ranking field, never `detections` times the per-trace figure |
| `detections_gaps` | Sorted list of the reasons below |
| `detections_sampling_rate` | Number or `null`. The lowest sampling rate of the covered days. The Hub does not extrapolate |

On each finding only, `detections_from` and `detections_to` (`YYYY-MM-DD`) give the range of days actually counted.

- The unit is an emitted finding. One trace can emit several of the same signature.
- Acknowledged findings are counted by the Hub. The skill excludes them anyway.
- A `sources[]` entry may hold only counts, with `producer_version` and `age_seconds` set to `null`.

### Three states

| Value | State | Wording |
|-------|-------|---------|
| `null` | Unknown | "volume unknown", never zero |
| a number with `detections_complete` false | Lower bound | "at least", with the reasons from `detections_gaps` |
| a number with `detections_complete` true | Exact | the figure as is |

A sampled count can be extrapolated source by source, by dividing by `detections_sampling_rate`. "At least" applies to the counted figure only. The extrapolated one is "about N, extrapolated at the lowest sampling rate of the window (may overstate if the rate changed during it)": the Hub keeps only the lowest rate of the covered days.

### Window rule

- The window is whole UTC days, from `max(day(from), the Hub's retention cutoff day)` to `day(to)`, or to the Hub's current day without `to`.
- The window also selects the rows: a finding is listed only when it was seen or counted inside it, so one first seen today is absent from a window that ends yesterday.
- The current day is never complete (`open_day`).
- A daemon restart makes its day incomplete (`restart`): a week with a deployment gives a lower bound.
- Several pods behind one Service read by poll are never complete (`multi_instance`).

### Gaps

The closed set of `detections_gaps` values. Meanings come from the engine's design of the detection counter.

| Gap | Plain words |
|-----|-------------|
| `uncovered_days` | Some days of the window have no count from this source: the daemon was older than the counter, had it turned off, was not running, or its history did not reach that far |
| `open_day` | A day of the window is not closed yet, the current day always, or a day the daemon stopped before midnight |
| `restart` | The daemon started or stopped during a day, so the detections outside its run that day are missing |
| `sampling` | The daemon kept only part of the traces that day, so the count covers the sampled traces only |
| `shed` | The daemon dropped whole traces under load before analyzing them |
| `ingest_rejected` | The daemon refused incoming spans (queue full, memory pressure), so their detections were never made |
| `overflow` | The daemon hit its cap of tracked signatures that day, and this finding has no count that day: its detections may sit in the uncounted overflow |
| `multi_instance` | Several pods behind one Service are read by poll, and a poll reaches one pod at a time, so the count can never be complete. Remedy: push from each pod, or one source per pod |

## Links

- CLI, sign-in and `hub` commands: https://perf-sentinel.dev/docs/CLI#hub-login-logout-hub
- Acknowledgment workflows, daemon and TOML: https://perf-sentinel.dev/docs/ACK-WORKFLOW
- Acknowledgment file: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS

## Lab trial

2026-10-29, a local Hub 0.8.6 polling one perf-sentinel 0.37.1 daemon, with 12 planted N+1 and 9 redundant SQL traces. Covered: the skill, run headless in rank-only mode with a window including today, ranked both findings with the Hub's own figures (12 detections and 60 avoidable I/O, 9 and 18) as lower bounds with `open_day`, `restart` and `uncovered_days`, and saved its page to a file through a redirect without printing it. A read without a window ranks every volume as unknown. Not covered: complete days (the counter seals a day at UTC midnight), an ack under a signed-in identity (the open Hub answers `403`, the sign-in itself is the lab's `hub-access-control`), and a fix handed to `perf-tests`.

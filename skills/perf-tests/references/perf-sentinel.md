# Perf Sentinel facts

What the skill needs to know about Perf Sentinel: which spans it can use, what makes each detector fire, the gate defaults, the commands, the exit codes and the acknowledgment entry. Numbers are the defaults. A project can override them in `.perf-sentinel.toml`, so read that file first and fall back to this page only when it is absent. Check the linked page before relying on a value for an unusual case.

## What makes a span usable

Perf Sentinel reads a closed list of span attributes. A span that lacks the one it needs is dropped with no warning and no error, so a thin report can mean no problem or no usable instrumentation. Never read an empty report as a clean one.

| I/O kind | Needs | Notes |
|----------|-------|-------|
| SQL | `db.query.text` or `db.statement` | A non-SQL `db.system` (a document store, a cache) is dropped. A SQL span without the statement text is dropped. |
| HTTP | `url.full` or `http.url` | A SERVER span is never an outbound call, even with a URL. A span that sets no kind stays eligible. |
| RPC (gRPC, Dubbo) | `rpc.system` plus `rpc.service` or `rpc.method` | CLIENT spans only. Findings appear under the `_http` types. |
| Messaging | `messaging.system` plus the destination (`messaging.destination.name` or `messaging.destination`) | PRODUCER spans only. A CONSUMER span, or a CLIENT poll or settle span, is ignored. |

Attributes that enrich the findings without being required:

- `service.name` on the resource: the service in every finding and in the acknowledgment signature. Without it the service is `unknown`.
- `http.route` on server spans: the endpoint a finding is attributed to. Without it the endpoint falls back to the URL and the signature is less stable.
- `code.*` attributes: the source location and a framework-specific fix.
- `parent_span_id` (a real parent chain): fanout and serialized calls need it.

Links:

- Attribute list, RPC and messaging rules: https://perf-sentinel.dev/docs/INSTRUMENTATION#required-span-attributes
- Placeholder styles per driver: https://perf-sentinel.dev/docs/INSTRUMENTATION#sql-placeholder-styles-and-detection
- Sampling, which must be 100% in tests: https://perf-sentinel.dev/docs/INSTRUMENTATION#sampling-and-filtering
- Why instrumentation bounds the findings: https://perf-sentinel.dev/docs/LIMITATIONS#instrumentation-quality-bounds-findings

## Detectors

Defaults, evaluated per trace. Each threshold is a key of `[detection]` in `.perf-sentinel.toml`.

| Finding | Fires when | Severity |
|---------|-----------|----------|
| `n_plus_one_sql` | The same normalized query runs at least 5 times in one trace, with at least 5 distinct parameter sets, inside a 500 ms window (`n_plus_one_min_occurrences`, `window_duration_ms`) | Warning, Critical from 10 occurrences |
| `n_plus_one_http` | Same rule on one outbound HTTP or RPC target, distinct path or query values | Warning, Critical from 10 |
| `n_plus_one_messaging` | Same rule on one publish destination | Warning, Critical from 10 |
| `redundant_sql`, `redundant_http` | The same template with the same parameters, at least 2 times in one trace. A group already reported as an N+1 is not repeated here | Info under 5, Warning from 5 |
| `slow_sql`, `slow_http`, `slow_messaging` | At least 3 occurrences of one template slower than 500 ms (`slow_query_min_occurrences`, `slow_query_threshold_ms`) | Warning, Critical when the slowest exceeds 5 times the threshold |
| `excessive_fanout` | One parent span has more than 20 direct children (`max_fanout`). Needs `parent_span_id` | Warning, Critical above 3 times the limit |
| `chatty_service` | A trace makes more than 15 outbound HTTP calls (`chatty_service_min_calls`) | Warning, Critical above 3 times the limit |
| `pool_saturation` | A peak of 10 or more SQL spans of one service running at the same time (`pool_saturation_concurrent_threshold`) | Warning |
| `serialized_calls` | At least 3 sequential sibling calls with distinct templates and no time overlap under one parent (`serialized_min_sequential`) | Info |

What this means when sizing a test:

- The N+1 floor is 5 distinct values and the critical tier is 10. A test with 3 children never fires. The goal is the production shape, so the data volume comes from the developer's production numbers and 5 is only the floor.
- The 500 ms window is measured on the trace. A fast local database stays well inside it. A loop slowed by a throttled test environment can fall outside it and be missed.
- A Warning N+1 (5 to 9 occurrences) does not fail the default gate. Only a critical one (10 or more) trips `n_plus_one_sql_critical_max = 0`, besides the waste ratio. See `Gate defaults`.
- N+1 counts distinct parameter values. Same-parameter repeats are `redundant_*`, not N+1.
- Session statements a pooled driver emits at every connection checkout (`COMMIT`, `SET`) are skipped by the repetition detectors.
- Slow, fanout, chatty, pool saturation and serialized findings are structural. They do not count in the I/O waste ratio.

### Sanitized SQL and the reclassification

An agent or driver that replaces literals with a placeholder (`?`, `$1`, `%s`, `@p0`, `:name`) hides the parameters, so the standard rule sees one parameter set and reports `redundant_sql` instead of an N+1. Perf Sentinel recovers the N+1 with a heuristic, `[detection] sanitizer_aware_classification`:

- `auto` (default): reclassify as `n_plus_one_sql` when an ORM scope is on the spans (Spring Data, Hibernate, EF Core, SQLAlchemy and others) or when the span durations vary enough (coefficient of variation above 0.5, `sanitizer_aware_min_cv`). At least 3 spans are needed for the variance signal.
- `strict`: needs a primary signal (ORM scope, sequential siblings, or high occurrence) plus a corroborating one (timing variance or high occurrence). From 15 identical sanitized queries in a trace (3 times the minimum) it reclassifies on count alone. Below that, a cached repeat stays `redundant_sql`.
- `always` reclassifies every sanitized group of at least 5. `never` turns the heuristic off.

A reclassified finding carries `classification_method = "sanitizer_heuristic"` in the JSON.

When a test is meant to reproduce an N+1 and the report shows `redundant_sql`, suspect these cases before suspecting the test:

- **EF Core** (`@__param_0`) and **Hibernate** (`?`) bind parameters hide the values. Under `auto`, the N+1 still reads as `n_plus_one_sql` when the ORM scope is on the SQL spans or one of their parents (the OpenTelemetry EF Core instrumentation puts it on the span, a Spring Data repository span is a parent). Without that scope, it reads as `redundant_sql`, and the finding is still correct about the repeated query.
- **gRPC and other RPC**: the arguments live in the message body, so N distinct calls to one method read as `redundant_http`.
- **Redacted query strings**: .NET redacts the query of `url.full` by default (the runtime on .NET 9 and later, the OpenTelemetry instrumentation before). Calls that vary a query parameter then look identical and read as `redundant_http`. A loop that varies a path segment is not affected. The opt-outs are in the .NET reference.
- **Strict mode on a cached repeat** stays `redundant_sql` by design.
- **In a test**, count either `n_plus_one_sql` or `redundant_sql` on the looped template as the N+1 for EF Core, Hibernate bind parameters and bare drivers. Under the default `auto`, a bare driver with no ORM scope and uniform local timings stays `redundant_sql` at any count, because `auto` reads only the ORM scope and the duration spread, never the count. So that finding is the expected signal for the looped template, not a failed test. A count of 15 or more iterations (3 times the minimum) reclassifies it as `n_plus_one_sql` only when the project sets `sanitizer_aware_classification = "strict"`. Use at least 15 iterations on a bare driver so that `strict` reclassifies it too.

Links:

- Detection algorithms: https://perf-sentinel.dev/docs/design/04-DETECTION
- ORM bind parameters: https://perf-sentinel.dev/docs/LIMITATIONS#orm-bind-parameters-and-n1-vs-redundant-classification
- The `[detection]` keys: https://perf-sentinel.dev/docs/CONFIGURATION#detection

## Gate defaults

The quality gate is evaluated on every `analyze`. It only changes the exit code under `--ci`. Keys of `[thresholds]`:

| Key | Default | Fails when |
|-----|---------|------------|
| `n_plus_one_sql_critical_max` | `0` | There are more critical N+1 SQL findings than this, so one is enough |
| `n_plus_one_http_warning_max` | `3` | More than 3 N+1 HTTP findings of warning level or higher |
| `n_plus_one_messaging_warning_max` | `3` | More than 3 N+1 messaging findings of warning level or higher |
| `io_waste_ratio_max` | `0.30` | More than 30% of the analyzed I/O is avoidable (N+1 and redundant) |
| `min_usable_span_ratio` | unset | The share of analyzable I/O spans is below it. Off by default |

`min_usable_span_ratio` is the one to suggest enabling. It makes broken instrumentation fail the build instead of passing with zero findings:

- Batch runs only (`analyze`, `report`), on OTLP input only. Native, Jaeger and Zipkin files carry no tally.
- It is computed per I/O kind and the worst kind counts, so healthy HTTP cannot hide a blind SQL surface.
- A kind with fewer than 20 spans is not judged. When no kind reaches 20, the rule is skipped and the report says so in a warning.
- The figure is a fleet average, not a verdict per service. Leave headroom below 1.0.

Acknowledged findings leave the gate. An expired acknowledgment puts its finding back in.

Link: https://perf-sentinel.dev/docs/CONFIGURATION#thresholds

## Commands

### capture

`capture` receives OTLP and writes it to a file. It never analyzes. Wrap the existing test command with it, so the suite runs once:

```bash
perf-sentinel capture --output <file outside the build dir> -- <test command>
```

| Flag | Default | Use |
|------|---------|-----|
| `--output`, `-o` | required | The NDJSON file. Its directory is created if missing. Keep it outside the build directory, since a `clean` deletes it |
| `--listen-address` | `127.0.0.1` | `0.0.0.0` when the application runs in a container of the same job |
| `--listen-port-grpc` | `4317` | A port already taken on the machine |
| `--listen-port-http` | `4318` | Same |
| `--max-file-size` | `512` (MiB) | A large suite. Past the cap the file is valid but incomplete and the run exits 2 |
| `--grace-ms` | `2000` | Time kept listening after the command exits, for the exporter's last flush |

- The command after `--` runs directly, not through a shell. Put a pipeline or an `&&` chain in a script and wrap the script.
- The ports are bound before the command starts. Progress and the final count go to stderr, which tells "nothing was exported" from "no anti-patterns".
- Background form, only when the pipeline owns the test command and it cannot be prefixed: `perf-sentinel capture --output <file> &`, keep the pid, run the tests, then `kill -TERM $pid && wait $pid`.
- Application side: set `OTEL_EXPORTER_OTLP_ENDPOINT` and also an explicit `OTEL_EXPORTER_OTLP_PROTOCOL`. SDKs disagree on their default, and an endpoint aimed at the wrong protocol exports nothing without saying so. `grpc` goes to port 4317, `http/protobuf` to port 4318. Sample at 100%.
- A port already taken makes `capture` exit 1 before the command starts. Rerun on free ports and move the exporter endpoint to match.
- Application in a container: the container reaches `capture` through `host.docker.internal`, with `OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318` and `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` set inside it. Variables set on `capture` do not reach a container, so pass them with `docker run -e`.
  - `--listen-address 0.0.0.0` opens an unauthenticated OTLP receiver on every interface. Keep it for ephemeral CI runners.
  - On a developer machine, prefer a narrower address. Docker Desktop resolves `host.docker.internal` by itself and reaches `127.0.0.1`, so the default works. On Linux, `host.docker.internal` resolves only with `docker run --add-host=host.docker.internal:host-gateway`, and it points at the docker bridge gateway, so bind that address (`--listen-address <gateway address>`).

### analyze

```bash
perf-sentinel analyze --input <file> [--config .perf-sentinel.toml] [--format json|sarif] [--ci]
```

- Without `--format` the output is the colored text report. With `--ci` the output is JSON and the exit code reflects the gate.
- Add `--config .perf-sentinel.toml` when the project has one. Every tuning knob lives in that file, none is a flag.
- `--acknowledgments <path>` overrides `./.perf-sentinel-acknowledgments.toml`. `--no-acknowledgments` shows everything. `--show-acknowledged` includes the acknowledged findings with their metadata.
- Reads stdin when `--input` is omitted. The input format is detected (native JSON, OTLP, Jaeger, Zipkin, the capture NDJSON).

Checking that the capture is usable, from `--format json`:

- `analysis.events_processed` and `analysis.traces_analyzed`: both above zero.
- `analysis.ingest`, present on OTLP input: `spans_received`, `spans_filtered`, `usable_span_ratio`, and the per-reason counters `filtered_missing_db_statement` and `filtered_missing_http_url`. A high count there means the spans lack the SQL text or the URL.
- A text search of the capture file for the diff's table names or endpoint.

An empty capture file makes `analyze` exit 75, never a clean gate.

Link: https://perf-sentinel.dev/docs/INTEGRATION#events-received-but-no-findings

### report

```bash
perf-sentinel report --input <file> --output <file.html> [--config .perf-sentinel.toml]
```

The self-contained HTML dashboard, readable offline. It exits 0 even when the gate fails, the gate shows as a badge. SARIF and JSON come from `analyze --format`, HTML only from `report`.

It is not interactive, so the skill can run it. Write it next to the capture file, outside the build directory, and give the developer its path to open in a browser. With Docker, the output path is inside the mounted repository: `docker run --rm -v "$PWD:/work" -w /work robintrassard/perf-sentinel:<version> report --input <file> --output <file.html>`.

### diff

```bash
perf-sentinel diff --before <base-capture> --after <head-capture> [--config ...] [--format text|json|sarif]
```

The delta between two captures, for pull request regressions. An acknowledged finding is filtered from both sides, so its fix never shows as resolved.

### inspect

`perf-sentinel inspect` is an interactive terminal UI. It needs a terminal and exits 1 without one, so never run it from the skill. Use the JSON check above.

The developer can open it on a capture: `perf-sentinel analyze --tui --input <file>` starts on the summary, `Enter` goes down to Inspect then Explain, `Esc` back up, `q` quits. With Docker, add `-it`: `docker run --rm -it -v "$PWD:/work" -w /work robintrassard/perf-sentinel:<version> analyze --tui --input <file>`.

### Install

Use the official GitHub release asset and verify it against the published `SHA256SUMS.txt` before running it:

```bash
DEST=$(mktemp -d) && cd "$DEST"
BASE_URL=https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/releases/latest/download
curl -sSLf -o perf-sentinel-linux-amd64 "$BASE_URL/perf-sentinel-linux-amd64"
curl -sSLf -o SHA256SUMS.txt "$BASE_URL/SHA256SUMS.txt"
grep 'perf-sentinel-linux-amd64' SHA256SUMS.txt | sha256sum -c -
chmod +x perf-sentinel-linux-amd64
```

The download goes to a temporary directory, never to the developer's repository. Ask where to put the binary: a directory on the `PATH`, or a folder of the developer's choice (`Local run modes`).

Pick the asset that matches the platform from the release page, and use `shasum -a 256 -c -` where `sha256sum` is missing. Never use a third-party mirror. Ask before installing anything.

### Local run modes

On a developer machine there are three ways to run Perf Sentinel. The developer picks one, nothing is installed before that.

| Mode | When | How it is called |
|------|------|------------------|
| Binary on the `PATH` | Perf Sentinel is used often, on several repositories | `perf-sentinel ...`, installed as in `Install` |
| Binary in a folder | Nothing goes on the `PATH`, or a version is kept per project | By its path, for example `~/tools/perf-sentinel/perf-sentinel ...`, downloaded and checked as in `Install`. A folder inside the repository must be ignored by git |
| Docker image | Docker is already there and nothing should be installed | `docker run ... robintrassard/perf-sentinel:<version> ...` (Docker Hub), or `ghcr.io/institut-du-numerique-responsable/perf-sentinel:<version>`. Pin the version, never `latest` |

The config file, in every mode: without `--config`, Perf Sentinel reads `.perf-sentinel.toml` from the directory it runs in, when the file is there. So run it from the repository root, or pass `--config <path>`. With `--config` the file becomes required: a missing one exits 75 instead of falling back to the defaults.

With Docker, the image holds the binary alone (`FROM scratch`, entrypoint `/perf-sentinel`, user 65534):

- `capture` only in the background form. `capture -- <test command>` would run the tests inside the empty image. Start the receiver, run the tests on the machine, then stop it:

  ```bash
  docker run -d --name perf-sentinel-capture \
    -p 127.0.0.1:4317:4317 -p 127.0.0.1:4318:4318 \
    -v "$PWD/<capture dir>:/out" \
    robintrassard/perf-sentinel:<version> \
    capture --output /out/traces.ndjson --listen-address 0.0.0.0
  # run the tests, exporting to http://127.0.0.1:4318 with OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
  docker stop perf-sentinel-capture
  docker logs perf-sentinel-capture
  docker rm perf-sentinel-capture
  ```

  `--listen-address 0.0.0.0` applies inside the container, and the `127.0.0.1:` of `-p` keeps the receiver closed to the network. `docker stop` sends SIGTERM: `capture` keeps listening for its grace (2 s by default), writes the file and exits 0. `docker logs` shows the span count.
- `analyze`, `report` and `diff` read the repository through a mount, from its root, so `.perf-sentinel.toml` is found:

  ```bash
  docker run --rm -v "$PWD:/work" -w /work robintrassard/perf-sentinel:<version> \
    analyze --input <capture dir>/traces.ndjson --format json
  ```

- On Linux, add `--user "$(id -u):$(id -g)"` to both commands, so the container can write the capture file and the developer owns it. Docker Desktop on macOS needs nothing.

Links:

- Capture reference: https://perf-sentinel.dev/docs/CLI#capture
- CI recipes: https://perf-sentinel.dev/docs/CI#ci-integration-recipes

## Exit codes

`analyze` and the other batch commands:

| Code | Meaning |
|------|---------|
| `0` | Success. Under `--ci`, the gate passed |
| `1` | Gate failed. Only `analyze --ci` emits it |
| `2` | Usage error: a missing flag or an unsupported flag combination |
| `75` | Tooling error: a missing, unreadable, empty or malformed input, config or acknowledgments file, or a failure writing the output. Never a gate breach |

`capture`:

| Code | Meaning |
|------|---------|
| `0` | Capture completed. This holds even when nothing was received, so the trace check of `analyze` still has to run |
| the command's own code | The wrapped command failed. A command killed by a signal gives `128 + signal` |
| `1` | The capture itself failed (port taken, unwritable file), before the command started |
| `2` | The file is incomplete: the size cap was hit or requests could not be queued fast enough. Any verdict from it understates the run |

Link: https://perf-sentinel.dev/docs/CI#exit-codes

## Acknowledgment entry

For a finding the developer decides to keep, propose this entry for `.perf-sentinel-acknowledgments.toml`, versioned in the repository. An acknowledged finding is filtered from the output and excluded from the gate.

```toml
[[acknowledged]]
signature = "<from the analyze JSON>"
acknowledged_by = "<REPLACE: the reviewer's name or handle>"
acknowledged_at = "<today, YYYY-MM-DD>"
reason = "<why it stays, with a link to the ticket or the decision>"
expires_at = "<YYYY-MM-DD>"     # always set: an entry without a date is permanent
service = "<the finding's service, verbatim>"
source_endpoint = "<the finding's source_endpoint, verbatim>"
```

- Get the signature, and the `service` and `source_endpoint` values, from the same JSON: `perf-sentinel analyze --input <file> --format json | jq '.findings[] | {signature, service, source_endpoint}'`. The signature has the form `<finding_type>:<service>:<sanitized_endpoint>:<32 hex chars>`.
- `signature`, `acknowledged_by`, `acknowledged_at` and `reason` are required. A missing one fails the run. An empty `acknowledged_by` is accepted without error, so the developer must replace the placeholder, nothing will flag it. `expires_at` is validated at load time.
- Fill `service` and `source_endpoint` so that the unmatched warning can tell "fixed" from "did not run".
- One signature covers every recurrence of the same template on the same service and endpoint.
- A fresh analysis reports an entry that suppressed nothing as the warning kind `unmatched_acknowledgment`, in the text output and in `warning_details` of the JSON. When the entry carries both `service` and `source_endpoint`, "the problem looks fixed" means the entry can be removed. "This proves nothing" means the endpoint emitted no I/O, so keep it. An expired entry is never reported, since it is inactive and its finding is back in the gate.
- A signature changes when the service name or the endpoint attribution changes, so an upgrade of the instrumentation can orphan an entry.

Link: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS

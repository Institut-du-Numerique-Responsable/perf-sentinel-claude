# Rust

Status: written from official docs, not yet tried

## Recommended instrumentation

- Library first. The Rust docs describe no agent, so use the `tracing` crate for spans, bridged to OpenTelemetry.
- Crates: `tracing`, `tracing-subscriber`, `tracing-opentelemetry`, `opentelemetry`, `opentelemetry_sdk`, `opentelemetry-otlp`.
- Traces are Beta upstream (the OpenTelemetry Rust status page lists traces as Beta, metrics and logs as Stable). Say so to the developer, the API can still move.
- `opentelemetry-otlp` has one feature per transport: `grpc-tonic` for port 4317, an HTTP feature for port 4318. Pick one and set the matching protocol in code.
- Check the current version of every crate on docs.rs, and keep the OpenTelemetry crates on matching versions. Write no version number from this file.
- Nothing instruments the database for you. Plan to write the SQL spans by hand (next section).

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** The `tracing` span needs the fields Perf Sentinel reads: `db.statement` (or `db.query.text`) with the SQL, and `db.system`. Fields whose names start with `otel.` are reserved by `tracing-opentelemetry` (`otel.kind`, `otel.name`), every other field becomes a span attribute.
  - **Diesel**: set an `Instrumentation` with `diesel::connection::set_default_instrumentation`. Its `on_connection_event` receives `StartQuery` and `FinishQuery` with the query. Open a span on the first and close it on the second, with the fields above. Diesel and SeaORM are in Perf Sentinel's ORM scope list.
  - **SeaORM**: it emits no span with the SQL. Wrap the calls in a span carrying the fields.
  - **sqlx**: `ConnectOptions::log_statements` logs statements as `tracing` events at the chosen level. Events are not spans, so Perf Sentinel never sees them. Wrap the query in a span by hand. A community wrapper may exist, none is verified here.
- [ ] **Outbound HTTP.** A client span needs the full URL (`url.full` or `http.url`) and a client kind: `otel.kind = "client"`. Unverified: an HTTP client crate emits no span unless a separate instrumentation crate adds one. Check the capture, otherwise wrap the call in a span.
- [ ] **`http.route`.** Server spans come from the web framework's own tracing layer, if any. Check a server span, and add `http.route` by hand if it is absent.
- [ ] **`service.name`.** On the SDK resource, or `OTEL_SERVICE_NAME`.
- [ ] **Parent chain.** Async code needs `.instrument(span)` or `#[tracing::instrument]`, otherwise the SQL span is not a child of the request span and fanout detection loses its parent.

## Turning export on in tests

Build the exporter and provider once, then add the layer to a `tracing_subscriber::registry()`:

- Exporter: `opentelemetry_otlp::SpanExporter::builder().with_tonic()` (or `.with_http()` with `.with_protocol(Protocol::HttpBinary)`), then `SdkTracerProvider::builder().with_batch_exporter(exporter).build()`.
- Layer: `tracing_opentelemetry::layer().with_tracer(provider.tracer("<name>"))`. Take the tracer from the provider, as the Perf Sentinel recipe does, rather than from `global::tracer()`, to avoid a `PreSampledTracer` trait bound error.
- `opentelemetry-otlp` reads `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_PROTOCOL` (the protocol needs the matching crate feature). For HTTP the `/v1/traces` path is appended to the general variable. Set both variables, so the code does not hard-code a port.
- Init once for the whole test binary: `std::sync::OnceLock` or `Once`. A second `.init()` of the global subscriber panics, and tests in one binary share the process.
- Hold the provider in the same place and call `provider.shutdown()` (or `force_flush()`) once all tests are done. The official getting-started does the same before exit.

## Test-time traps

- **Subscriber set twice.** `.init()` in each `#[test]` panics on the second. Use `try_init()` or a `OnceLock`.
- **Provider dropped before flush.** The batch processor holds spans. With no `shutdown()` at the end, the last spans vanish. A binary that ends with `std::process::exit` skips drops.
- **`#[tokio::test]` runtimes.** Each test gets its own runtime that ends with the test. Whether the batch exporter survives that depends on the SDK release and its runtime feature. Unverified: flush or run on a shared runtime, and check the capture is complete.
- **Spans never created.** `RUST_LOG` or an `EnvFilter` that excludes the span's target drops them before the OpenTelemetry layer. Keep the filter permissive for the span's target.
- **Fields declared after creation.** A `tracing` field not declared when the span is created cannot be set later with `record`. Declare `db.statement` as `tracing::field::Empty`, or give it a value at creation.
- **`sqlx` events.** See above, they never reach Perf Sentinel.
- **Wrong transport for the port.** gRPC to 4318 or HTTP to 4317 exports nothing and says nothing useful.
- **Parameters read as `redundant_sql`.** Rust drivers send placeholders. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- `perf-sentinel capture --output <file> -- cargo test <filter>`. The exporter variables set for `capture` are inherited by `cargo test` and the test binary.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file. A first run on this stack has hand-written SQL spans, so read them in the capture before trusting a green result.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- OpenTelemetry Rust, status and releases: https://opentelemetry.io/docs/languages/rust/
- OpenTelemetry Rust, exporters: https://opentelemetry.io/docs/languages/rust/exporters/
- OpenTelemetry Rust, getting started: https://opentelemetry.io/docs/languages/rust/getting-started/
- `tracing-opentelemetry`, special fields: https://docs.rs/tracing-opentelemetry/latest/tracing_opentelemetry/
- `opentelemetry-otlp`, transports and variables: https://docs.rs/opentelemetry-otlp/latest/opentelemetry_otlp/
- Diesel, `Instrumentation`: https://docs.rs/diesel/latest/diesel/connection/trait.Instrumentation.html
- Diesel, `set_default_instrumentation`: https://docs.rs/diesel/latest/diesel/connection/fn.set_default_instrumentation.html
- sqlx, `ConnectOptions`: https://docs.rs/sqlx/latest/sqlx/trait.ConnectOptions.html
- Perf Sentinel, Rust: https://perf-sentinel.dev/docs/INSTRUMENTATION#rust-tracing-opentelemetry-031-diesel-seaorm

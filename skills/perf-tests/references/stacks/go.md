# Go

Status: written from official docs, not yet tried

## Recommended instrumentation

- Library first. Go has no agent that fits a test run: the zero-code options (eBPF, compile-time) are documented as work in progress. Wrap the libraries in code.
- Core: `go.opentelemetry.io/otel`, `.../otel/sdk`, and one OTLP trace exporter: `.../exporters/otlp/otlptrace/otlptracegrpc` (port 4317) or `.../otlptracehttp` (port 4318).
- HTTP: `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp`. `otelhttp.NewHandler` (or `NewMiddleware`) for the server, `otelhttp.NewTransport` around the client's `RoundTripper` for outbound calls.
- SQL, pick the one that matches the data layer:
  - `database/sql`: `github.com/XSAM/otelsql` (`otelsql.Open`, `otelsql.OpenDB`, `otelsql.Register`, `otelsql.WrapDriver`).
  - pgx: `github.com/exaring/otelpgx` (`cfg.ConnConfig.Tracer = otelpgx.NewTracer()` on the pool config).
  - GORM: `gorm.io/plugin/opentelemetry/tracing` (`db.Use(tracing.NewPlugin())`).
- If the project already uses one of these, keep it. Do not add a second SQL layer on the same connection.
- Check the current version of every module on its page. Write no version number from this file.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** otelpgx and the GORM plugin set the statement text on the span, otelsql does unless `WithDisableSQLStatementInAttributes()` is set. The attribute name depends on the release (`db.statement` or `db.query.text`), Perf Sentinel reads both. The docs do not name it, check the capture. pgx sends `$1` placeholders, which Perf Sentinel normalizes.
- [ ] **GORM variables.** `tracing.WithoutQueryVariables()` keeps the values out of the text. Leave it off in tests, so distinct parameters stay visible. The default plugin also records metrics, `tracing.WithoutMetrics()` turns them off.
- [ ] **Outbound HTTP.** Only calls made through a client whose transport is wrapped with `otelhttp.NewTransport` are traced. A bare `http.DefaultClient` is invisible.
- [ ] **`http.route`.** otelhttp's span name formatter sees the request `Pattern` when the router (`http.ServeMux`, or a middleware that sets it) provides one. Whether the `http.route` attribute is set depends on the router and the release, check a server span.
- [ ] **`service.name`.** On the resource: `semconv.ServiceName("<name>")` merged into `resource.Default()`, or `OTEL_SERVICE_NAME`.
- [ ] **Sampling.** The SDK default is `ParentBased(AlwaysSample)`, which is 100%. Do not add a ratio sampler.

## Turning export on in tests

Build the tracer provider once, register it globally, instrument the server and the DB, and shut the provider down at the end of the run. The official getting-started shows the shape: `sdktrace.NewTracerProvider(sdktrace.WithBatcher(exp), sdktrace.WithResource(r))`, then `otel.SetTracerProvider(tp)`, then `tp.Shutdown(ctx)`.

- The OTLP packages read `OTEL_EXPORTER_OTLP_ENDPOINT` (and the `_TRACES_` form, which wins). Their default is `https://localhost`, with TLS.
- Plaintext to `perf-sentinel capture`: for gRPC, pass `otlptracegrpc.WithInsecure()` or give an endpoint without a scheme and set `OTEL_EXPORTER_OTLP_INSECURE=true`. For HTTP, use an `http://` endpoint.
- The protocol is the package you import, not a variable. The `OTEL_EXPORTER_OTLP_PROTOCOL` variable does nothing unless the project uses `autoexport`.
- For `otlptracehttp`, `OTEL_EXPORTER_OTLP_ENDPOINT` takes the base URL and `/v1/traces` is appended.
- Put the setup in `TestMain`. Call `tp.Shutdown(ctx)` after `m.Run()` and before `os.Exit`, because `os.Exit` skips deferred calls.

## Test-time traps

- **TLS by default.** An exporter pointed at the plaintext capture without `WithInsecure` or an `http://` URL exports nothing and logs only to the OTel error handler.
- **Last batch lost.** `WithBatcher` holds spans until its schedule. Without `Shutdown` (or `ForceFlush`) in `TestMain`, the end of the run is lost.
- **Provider not registered globally.** Libraries that use the global provider (otelhttp, otelsql by default) export nothing. Either call `otel.SetTracerProvider`, or pass the provider with each library's `WithTracerProvider` option.
- **Handler under test not wrapped.** A test that calls the handler function directly skips `otelhttp.NewHandler`. Wrap it, or start the server with `httptest.NewServer` around the wrapped handler.
- **Context not passed.** A query run with `context.Background()` instead of the request's context starts a new trace and joins no parent. Pass `r.Context()` down to every `QueryContext` and `db.WithContext(ctx)` call.
- **Two SQL layers.** GORM over otelsql or otelpgx can emit two spans per statement. Unverified: look for every query twice in the capture and keep one source if so.
- **Parameters read as `redundant_sql`.** pgx sends placeholders. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- `perf-sentinel capture --output <file> -- go test ./... -run <new tests>`. Add `-count=1` so the Go test cache does not replay a cached pass that exported nothing.
- The exporter variables set for `capture` are inherited by `go test`.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- OpenTelemetry Go, instrumentation and tracer provider: https://opentelemetry.io/docs/languages/go/instrumentation/
- OpenTelemetry Go, exporters: https://opentelemetry.io/docs/languages/go/exporters/
- Go zero-code instrumentation status: https://opentelemetry.io/docs/zero-code/go/
- otelhttp: https://pkg.go.dev/go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp
- otlptracegrpc, endpoint and TLS variables: https://pkg.go.dev/go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc
- otlptracehttp: https://pkg.go.dev/go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp
- SDK trace, default sampler: https://pkg.go.dev/go.opentelemetry.io/otel/sdk/trace
- otelsql: https://github.com/XSAM/otelsql
- otelpgx: https://github.com/exaring/otelpgx
- GORM OpenTelemetry plugin: https://github.com/go-gorm/opentelemetry
- Perf Sentinel, Go: https://perf-sentinel.dev/docs/INSTRUMENTATION#go-otelhttp-068--otelpgx-011-otel-sdk-143

# Java, Micronaut

Status: written from official docs, not yet tried

## Recommended instrumentation

- Library first: the Micronaut Tracing OpenTelemetry modules, declared as dependencies, no agent.
  - `io.micronaut.tracing:micronaut-tracing-opentelemetry-http` for HTTP server and client spans.
  - `io.micronaut.tracing:micronaut-tracing-opentelemetry-jdbc` for one span per JDBC query on the `DataSource` beans.
  - `io.opentelemetry:opentelemetry-exporter-otlp` for the exporter. Versions come from the Micronaut platform BOM. If the project overrides the tracing version, import the matching `micronaut-tracing-bom` too.
- If the project already runs the OpenTelemetry Java agent, keep it for this PR and mention the Micronaut modules as a separate migration. Do not run both in one JVM.
- Perf Sentinel has no Micronaut section. The Micronaut guide is the only source, so everything below that the guide does not state is to be checked in the traces.
- Write no version number from this file. Read the current ones on the official page.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** The JDBC module wraps the datasource. The guide does not say which attribute carries the statement. Check the capture for `db.statement` or `db.query.text`.
- [ ] **Outbound HTTP.** The HTTP module covers server and client requests. Check that client spans carry the full URL.
- [ ] **`http.route`.** Not stated in the guide. Check that server spans carry it, otherwise findings group by raw path.
- [ ] **`service.name`.** Defaults to the application name. `otel.service.name` overrides it.
- [ ] **Sampling 100%.** The guide does not cover sampling, the SDK autoconfigure property does: `otel.traces.sampler=always_on`. The SDK default is `parentbased_always_on`, set it anyway.

## Turning export on in tests

`otel.traces.exporter` defaults to `none` in Micronaut, so nothing leaves the JVM until the tests set it:

```properties
otel.traces.exporter=otlp
otel.exporter.otlp.protocol=grpc
otel.exporter.otlp.endpoint=http://localhost:4317
otel.traces.sampler=always_on
otel.metrics.exporter=none
otel.logs.exporter=none
```

- Set the protocol, the port follows it: `grpc` 4317, `http/protobuf` 4318. The SDK autoconfigure property `otel.exporter.otlp.protocol` is documented on opentelemetry.io, not on the Micronaut page.
- The guide shows an `OTEL_*` environment variable for resource attributes (`OTEL_RESOURCE_ATTRIBUTES`). Setting the exporter the same way, from the test task or the CI step, is a convenience the guide does not state: check in the capture that it took effect.
- Add `opentelemetry-exporter-otlp` to the test runtime if it is missing, the guide asks for it for every exporter you name.

## Test-time traps

- **Exporter `none`.** The default. A green test with no spans is the usual symptom.
- **Missing exporter dependency.** Naming `otlp` without `opentelemetry-exporter-otlp` on the classpath exports nothing.
- **Missing JDBC or HTTP module.** Each module adds its own spans. SQL absent while HTTP is present means `micronaut-tracing-opentelemetry-jdbc` is not on the test classpath.
- **Tracing version overridden alone.** The guide warns that overriding only the tracing module can resolve incompatible OpenTelemetry artifacts. Import the matching BOM.
- **Wrong protocol for the port.** gRPC to 4318 or HTTP to 4317 exports nothing and says nothing useful.
- **Parameters read as `redundant_sql`.** See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- Maven: `perf-sentinel capture --output <file outside target/> -- mvn verify`. Gradle: wrap `./gradlew test`.
- `perf-sentinel capture` is the target. Do not use a logging or stdout exporter, a forked test JVM cannot hand its stdout to the build.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file. A first run through this stack has no Perf Sentinel precedent, so read the spans themselves before trusting a green result.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- Micronaut Tracing, OpenTelemetry: https://micronaut-projects.github.io/micronaut-tracing/latest/guide/
- OpenTelemetry Java SDK configuration: https://opentelemetry.io/docs/languages/java/configuration/
- OTLP exporter variables: https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/

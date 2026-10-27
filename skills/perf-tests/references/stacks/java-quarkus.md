# Java, Quarkus

Status: written from official docs, not yet tried

## Recommended instrumentation

- Library first: the `quarkus-opentelemetry` extension. Quarkus's guide says the OpenTelemetry Java agent is neither needed nor recommended, and it does not work in native mode.
- If the project already runs the agent, keep it for this PR and mention the extension as a separate migration. Do not run both.
- JDBC: set `quarkus.datasource.jdbc.telemetry=true`. The extension wraps the datasource, so no driver change is needed. Statements are traced and connection acquisition is not, unless `quarkus.datasource.jdbc.telemetry.trace-connection=true`.
- Check the current Quarkus version and the extension on the official page. Write no version number from this file.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** The JDBC instrumentation emits one span per query. The docs do not name the attribute. Check in the capture that the spans carry `db.statement` or `db.query.text`, otherwise Perf Sentinel drops them.
- [ ] **Outbound HTTP.** The guide lists switches such as `quarkus.otel.instrument.resteasy-client` and `quarkus.otel.instrument.rest`, leave them on. Check that the client spans carry the full URL.
- [ ] **`http.route` and `service.name`.** `quarkus.otel.service.name` or the artifact id by default. Whether server spans carry `http.route` is not on the official page, check the traces.
- [ ] **Sampling.** The default sampler is `parentbased_always_on`, so everything is sampled. Set `quarkus.otel.traces.sampler=always_on` anyway so a leftover `traceidratio` from a profile cannot thin the traces.

## Turning export on in tests

Quarkus defaults to OTLP over gRPC to `http://localhost:4317`. Set the protocol explicitly, because the port follows it:

```properties
quarkus.otel.exporter.otlp.endpoint=http://localhost:4317
quarkus.otel.exporter.otlp.protocol=grpc
quarkus.otel.traces.sampler=always_on
quarkus.otel.metrics.exporter=none
quarkus.otel.logs.exporter=none
```

- With `http/protobuf` use port 4318.
- Keep these in a `%test.` profile line (`%test.quarkus.otel.exporter.otlp.endpoint=...`) or pass them as environment variables (`QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT`). The `%test` profile applies to `@QuarkusTest`.
- `quarkus.otel.simple=true` exports each span as it ends instead of batching. It is a cheap way to avoid losing the last spans at shutdown.
- The official guide has no testing section for exporting from tests. It only shows an in-memory exporter wired through CDI, which Perf Sentinel never sees. Say so when the developer asks, and check the capture.

## Test-time traps

- **In-memory exporter.** The default `quarkus.otel.traces.exporter` is `cdi`. A test that provides an `InMemorySpanExporter` bean replaces the OTLP sender. Remove it for the capture run.
- **`@QuarkusIntegrationTest` runs the built artifact** as a separate process, in the `prod` profile by default. A `%test.` setting does not reach it. Use environment variables or `quarkus.test.integration-test-profile`.
- **`quarkus.otel.enabled` or `quarkus.otel.sdk.disabled` set by a profile.** Both turn the extension off. Check the effective values.
- **Datasource telemetry off.** `quarkus.datasource.jdbc.telemetry` defaults to `false`. Without it there are no SQL spans and no finding, with no error. Named datasources need their own line (`quarkus.datasource."name".jdbc.telemetry=true`).
- **Wrong protocol for the port.** gRPC to 4318 or HTTP to 4317 exports nothing and says nothing useful.
- **Dev Services.** The OpenTelemetry Dev Service starts a Grafana LGTM stack in dev mode. If it is on the project, switch it off (`quarkus.observability.lgtm.enabled=false`) so the capture gets the traffic, not a second collector.
- **Parameters read as `redundant_sql`.** See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- Maven: `perf-sentinel capture --output <file outside target/> -- mvn verify` (or `mvn test` for `@QuarkusTest`). Gradle: wrap `./gradlew test` or `quarkusIntTest`.
- Export is OTLP over the network, not stdout, so the Surefire fork channel is not an issue here.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file. Zero SQL spans with healthy HTTP spans points at `quarkus.datasource.jdbc.telemetry`.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- Quarkus OpenTelemetry guide: https://quarkus.io/guides/opentelemetry
- Quarkus OpenTelemetry tracing guide: https://quarkus.io/guides/opentelemetry-tracing
- Quarkus datasource, tracing: https://quarkus.io/guides/datasource
- Quarkus testing guide: https://quarkus.io/guides/getting-started-testing
- Quarkus configuration reference, profiles: https://quarkus.io/guides/config-reference
- OTLP exporter variables: https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/
- Perf Sentinel, Quarkus: https://perf-sentinel.dev/docs/INSTRUMENTATION#java-quarkus-333-lts--quarkus-opentelemetry--otel-agent-v227

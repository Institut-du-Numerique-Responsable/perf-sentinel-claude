# Node.js

Status: written from official docs, not yet tried

## Recommended instrumentation

- Library first: `@opentelemetry/sdk-node` configured in a tracing file, with `@opentelemetry/auto-instrumentations-node` (the bundle of instrumentations, which includes `http`, `undici` for `fetch`, `pg`, `mysql2`, `knex` and `nestjs-core`) and an OTLP trace exporter. The zero-code form (`--require @opentelemetry/auto-instrumentations-node/register`) is the fallback, because instrumentation options cannot be set through environment variables.
- If the project already uses the `register` module, keep it for this PR and mention the programmatic file as a separate migration.
- NestJS needs nothing extra, the bundle covers it.
- Prisma: add `@prisma/instrumentation` and `new PrismaInstrumentation()` to the instrumentations list. It emits `prisma:client:*` spans and a `prisma:engine:db_query` span per query, with the query in its attributes.
- Exporter package: `@opentelemetry/exporter-trace-otlp-proto` or `-http` (port 4318, the default URL is `http://localhost:4318/v1/traces`), or `-grpc` (port 4317).
- Check the current version of every package on its page, and keep the OpenTelemetry packages on matching lines. Write no version number from this file.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** `@opentelemetry/instrumentation-pg` records the query as `db.query.text` in recent releases and `db.statement` before 0.72. Perf Sentinel reads both. Its README says `enhancedDatabaseReporting` attaches query parameters and results as attributes, and does not say the query text needs it. Try without it first and check the capture. Turn it on only with test data, since values land in the spans.
- [ ] **Prisma.** The query is on the `prisma:engine:db_query` span. Check that the capture holds that attribute with the SQL text. With a Prisma release that uses a driver adapter over `pg`, whether the `pg` instrumentation also emits spans is unverified: look for doubled queries.
- [ ] **Outbound HTTP.** The `http` and `undici` instrumentations set the full URL. Check that `fetch` calls appear.
- [ ] **`http.route`.** The `http` instrumentation does not know the route. The framework instrumentation (`express`, `nestjs-core`) adds it, check a server span.
- [ ] **`service.name`.** `OTEL_SERVICE_NAME`, or `serviceName` in `NodeSDK`.
- [ ] **Sampling.** The SDK default is `parentbased_always_on`, which is 100%.

## Turning export on in tests

Tracing file, loaded before the application:

```ts
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';

export const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter(),
  instrumentations: [getNodeAutoInstrumentations()],
});
sdk.start();
```

- Options for one instrumentation go in the map passed to `getNodeAutoInstrumentations({ '@opentelemetry/instrumentation-pg': { ... } })`.
- The exporter reads `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`. The proto and HTTP exporters append `/v1/traces` to the general variable. A `url:` passed in code must carry the full path.
- Load the file first:
  - CommonJS: `node --require ./tracing.js app.js`, or `NODE_OPTIONS`.
  - ESM: `--import ./tracing.mjs`, plus the loader hook `--experimental-loader=@opentelemetry/instrumentation/hook.mjs` that the official ESM page requires. Check that page, the recommendation is expected to change.
  - The `register` module under ESM: `node --experimental-loader=@opentelemetry/instrumentation/hook.mjs --import @opentelemetry/auto-instrumentations-node/register app.js`.
- Do not mix `--import` and `--require @opentelemetry/auto-instrumentations-node/register` in one `NODE_OPTIONS`. The official page warns about conflicts.
- Shut down at the end of the run: `await sdk.shutdown()` in the runner's global teardown, so the last batch is flushed.

## Test-time traps

- **Tracing file loaded after the app.** Instrumentations patch modules at load time. Anything `require`d or imported before `sdk.start()` stays unpatched, and no error says so.
- **Test runner sandboxes.** Jest and similar runners load test code through their own module system. Whether the patches apply there is not documented, check the capture and load the tracing file in the runner's setup or its `NODE_OPTIONS` if spans are missing.
- **ESM without the loader hook.** The app runs, nothing is patched.
- **`enhancedDatabaseReporting` and sensitive data.** It writes parameters into spans. Use test data only.
- **Last batch lost.** No `sdk.shutdown()`, no final spans.
- **Wrong exporter for the port.** The gRPC exporter to 4318 or the HTTP one to 4317 exports nothing and says nothing useful.
- **Parameters read as `redundant_sql`.** `pg` sends `$1` placeholders. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- `perf-sentinel capture --output <file> -- npm test -- <new tests>` (or the runner's own command).
- The exporter variables set for `capture` are inherited by the runner, and by the app if the test starts it as a child. An app started in a separate container needs the endpoint to reach the host, see [perf-sentinel.md](../perf-sentinel.md).
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- OpenTelemetry Node.js, getting started: https://opentelemetry.io/docs/languages/js/getting-started/nodejs/
- OpenTelemetry Node.js, exporters: https://opentelemetry.io/docs/languages/js/exporters/
- Zero-code Node.js: https://opentelemetry.io/docs/zero-code/js/
- ESM and CommonJS: https://github.com/open-telemetry/opentelemetry-js/blob/main/doc/esm-support.md
- `auto-instrumentations-node`: https://github.com/open-telemetry/opentelemetry-js-contrib/tree/main/packages/auto-instrumentations-node
- `instrumentation-pg`: https://github.com/open-telemetry/opentelemetry-js-contrib/tree/main/packages/instrumentation-pg
- SDK environment variables, sampler default: https://opentelemetry.io/docs/languages/sdk-configuration/general/
- Prisma, OpenTelemetry tracing: https://www.prisma.io/docs/orm/prisma-client/observability-and-logging/opentelemetry-tracing
- Perf Sentinel, Node.js: https://perf-sentinel.dev/docs/INSTRUMENTATION#nodejs-nestjs--prisma-otel-sdk-057

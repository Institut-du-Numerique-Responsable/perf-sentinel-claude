# .NET, ASP.NET Core

Status: tried end-to-end

## Recommended instrumentation

- Library first: the OpenTelemetry SDK configured in code. Microsoft's observability page calls it the most powerful and configurable path when you can rebuild the app. It also works with NativeAOT.
- Automatic instrumentation (the OpenTelemetry .NET startup hook) is the fallback, for an app you cannot edit. If the project already uses it, keep it for this PR and mention the SDK as a separate migration.
- Packages: `OpenTelemetry.Extensions.Hosting`, `OpenTelemetry.Instrumentation.AspNetCore`, `OpenTelemetry.Instrumentation.Http`, `OpenTelemetry.Exporter.OpenTelemetryProtocol`.
- SQL, pick the one that matches the data access layer:
  - SQL Server: `OpenTelemetry.Instrumentation.SqlClient` (`.AddSqlClientInstrumentation()`, stable).
  - Entity Framework Core: `OpenTelemetry.Instrumentation.EntityFrameworkCore` (`.AddEntityFrameworkCoreInstrumentation()`), a prerelease package, add it with `--prerelease`. Its breaking changes are tracked in its changelog.
  - Npgsql directly: `Npgsql.OpenTelemetry` (`.AddNpgsql()`), documented as experimental.
- Check the current version of every package on its page, and use versions that match each other. Read the package pages for target framework constraints. Write no version number from this file.
- Call the SQL instrumentations with no options for the statement text. `SetDbStatementForText` (and the stored procedure twin) was removed in newer releases of SqlClient and EF Core. Text is now always captured, with literals replaced by `?`. An old guide that sets it no longer compiles.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** SqlClient puts it in `db.query.text`. EF Core puts it in `db.statement` by default and in `db.query.text` with `OTEL_SEMCONV_STABILITY_OPT_IN=database`. Perf Sentinel reads both. A SqlClient stored procedure carries `db.stored_procedure.name` and no text, so it cannot be analyzed. Npgsql: its page does not name the attribute, check the capture.
- [ ] **Outbound HTTP.** The HttpClient instrumentation sets `url.full`. It replaces the values of the query string by `Redacted` by default, so a loop that varies a query parameter reads as repeated identical calls (`redundant_http`, not an N+1). Set `OTEL_DOTNET_EXPERIMENTAL_HTTPCLIENT_DISABLE_URL_QUERY_REDACTION=true` for the test run, or vary a path segment.
- [ ] **`http.route` and `service.name`.** The ASP.NET Core instrumentation sets `http.route`. Set `service.name` with `.ConfigureResource(r => r.AddService("<name>"))` or `OTEL_SERVICE_NAME`.
- [ ] **Sampling.** The default is `ParentBased(AlwaysOn)`, which is 100%. Do not add a sampler. If the project sets one, switch it to always on for tests.
- [ ] **EF Core N+1 classification.** Bind parameters (`@__param_0`, `@order_Id`) hide the values. With the EF Core instrumentation, its scope (`OpenTelemetry.Instrumentation.EntityFrameworkCore`) is on the SQL spans, so the default `auto` mode reports `n_plus_one_sql` with `classification_method = "sanitizer_heuristic"`. With SQL spans from the driver instrumentation only (SqlClient, Npgsql), no ORM scope is present and the N+1 can read as `redundant_sql`, still on the repeated query. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Turning export on in tests

Add `.AddOtlpExporter()` (or `UseOtlpExporter()`) to the tracing builder and set the endpoint and protocol by environment variable, so the code does not change between local, CI and capture:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

- The exporter's own default is gRPC, port 4317. For `http/protobuf` the port is 4318. Set the protocol anyway.
- `WebApplicationFactory` hosts the app in the test process, so the variables must be in the environment of that process before the host is built. Setting them on the `capture` command line is enough.
- With the endpoint set in code and HTTP/protobuf, the full URL must carry `/v1/traces`. With `UseOtlpExporter` the path is appended for you.
- If the app gates the exporter on a variable of its own (the Perf Sentinel recipe reads `OTLP_GRPC_ENDPOINT`), the variable must be set too, otherwise nothing is registered.

## Test-time traps

- **In-memory exporter.** `OpenTelemetry.Exporter.InMemory` stays in the process and never reaches Perf Sentinel. A test that swaps it in for assertions must not replace the OTLP exporter for the capture run.
- **Exporter registered conditionally.** An `if (endpoint is set)` guard in `Program.cs` means no variable, no spans, no error.
- **Last batch lost.** The batch processor flushes on provider shutdown. `WebApplicationFactory` disposes the host, and the host disposes the `TracerProvider`, when the factory is disposed. Keep the factory in an `IClassFixture` or `IAsyncLifetime` so it is disposed before the process exits, or call `TracerProvider.ForceFlush()` at the end of the run.
- **SQL missing but HTTP present.** The SQL instrumentation is not added to the builder, or the provider is a different SQL stack (SQLite, Dapper over a driver with no instrumentation). Check the capture for the diff's tables.
- **No SQL span right after startup.** EF Core caches for 1 second (`LoggingCacheTime`) whether anything listens to its diagnostics. Startup code that queries through EF Core before the `TracerProvider` subscribes (schema bootstrap, migrations, seeding in `Program.cs`) makes it cache "nobody listens", and test requests sent in that second emit no SQL span. The capture then holds only the server spans, with `filtered_missing_db_statement` at 0. Turn the cache off in the test factory only: `builder.ConfigureTestServices(s => s.ConfigureDbContext<AppDbContext>(o => o.ConfigureLoggingCacheTime(TimeSpan.Zero)))`.
- **Two SQL layers.** With EF Core over Npgsql or SqlClient, two instrumentations may each emit a span per statement. Unverified: look for every query twice in the capture and keep one source if so.
- **EF Core prerelease.** Attribute names can change between releases. Re-check the capture after an upgrade.

## Running the tests under capture

- `perf-sentinel capture --output <file outside bin/ and obj/> -- dotnet test --filter <new tests>`.
- The exporter variables set for the `capture` command are inherited by `dotnet test` and the host it runs.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- Microsoft, observability with OpenTelemetry: https://learn.microsoft.com/en-us/dotnet/core/diagnostics/observability-with-otel
- Microsoft, integration tests in ASP.NET Core: https://learn.microsoft.com/en-us/aspnet/core/test/integration-tests
- OpenTelemetry .NET, getting started: https://opentelemetry.io/docs/languages/dotnet/getting-started/
- OpenTelemetry .NET, customizing the SDK: https://github.com/open-telemetry/opentelemetry-dotnet/blob/main/docs/trace/customizing-the-sdk/README.md
- OTLP exporter for .NET: https://github.com/open-telemetry/opentelemetry-dotnet/blob/main/src/OpenTelemetry.Exporter.OpenTelemetryProtocol/README.md
- SqlClient instrumentation: https://github.com/open-telemetry/opentelemetry-dotnet-contrib/blob/main/src/OpenTelemetry.Instrumentation.SqlClient/README.md
- SqlClient changelog, `SetDbStatementForText` removal: https://github.com/open-telemetry/opentelemetry-dotnet-contrib/blob/main/src/OpenTelemetry.Instrumentation.SqlClient/CHANGELOG.md
- EF Core instrumentation: https://github.com/open-telemetry/opentelemetry-dotnet-contrib/blob/main/src/OpenTelemetry.Instrumentation.EntityFrameworkCore/README.md
- EF Core instrumentation changelog: https://github.com/open-telemetry/opentelemetry-dotnet-contrib/blob/main/src/OpenTelemetry.Instrumentation.EntityFrameworkCore/CHANGELOG.md
- HttpClient instrumentation: https://github.com/open-telemetry/opentelemetry-dotnet-contrib/blob/main/src/OpenTelemetry.Instrumentation.Http/README.md
- Npgsql tracing: https://www.npgsql.org/doc/diagnostics/tracing.html
- Perf Sentinel, ASP.NET Core and EF Core: https://perf-sentinel.dev/docs/INSTRUMENTATION#net-aspnet-core--entity-framework-core--opentelemetry-sdk-115

# Python, Django and FastAPI

Status: tried end-to-end

## Recommended instrumentation

- Library first: the OpenTelemetry SDK with the instrumentation packages for the project's frameworks, configured in code. The zero-code `opentelemetry-instrument` command is the fallback, and it breaks with several workers or a reloader (see the traps). If the project already uses it, keep it for this PR and mention the programmatic setup as a separate migration.
- Packages: `opentelemetry-sdk`, an OTLP exporter (`opentelemetry-exporter-otlp-proto-grpc` for port 4317, `opentelemetry-exporter-otlp-proto-http` for port 4318), then:
  - **Django**: `opentelemetry-instrumentation-django`, and `opentelemetry-instrumentation-psycopg` for SQL (`PsycopgInstrumentor().instrument()`).
  - **FastAPI**: `opentelemetry-instrumentation-fastapi` (`FastAPIInstrumentor.instrument_app(app)`) and `opentelemetry-instrumentation-sqlalchemy` (`SQLAlchemyInstrumentor().instrument(engine=engine)`). Add `opentelemetry-instrumentation-asyncpg` (`AsyncPGInstrumentor().instrument()`) when the driver is asyncpg.
  - Outbound HTTP: `opentelemetry-instrumentation-requests`, `-httpx` or `-aiohttp-client`, whichever the project uses.
- Check the current version of every package on its page. Install them at matching versions. Write no version number from this file.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **Order of setup.** Build the `TracerProvider`, call `trace.set_tracer_provider(provider)`, then call the `instrument()` methods. An instrumentor that runs first exports nothing, with no warning. Passing `tracer_provider=provider` to each `instrument()` also works.
- [ ] **SQL text.** The SQLAlchemy and asyncpg instrumentors put the statement in `db.statement` (asyncpg `$1` placeholders), checked in a capture. The Perf Sentinel recipe says the same for psycopg (DB-API `%s` placeholders), and Perf Sentinel recognizes both styles. Their `connect` spans carry no statement and count in `filtered_missing_db_statement`.
- [ ] **Async SQLAlchemy.** Instrument the sync engine under it: `SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)`.
- [ ] **SQLAlchemy over asyncpg.** The Perf Sentinel recipe installs both instrumentors. Then every statement gives two sibling spans, one per layer, and Perf Sentinel does not merge them (`filtered_merged_db_span: 0`). An N+1 over 50 rows reads as 100 occurrences, and every statement shows a `redundant_sql` Info with 2 occurrences. That Info is an instrumentation artifact, not a finding about the diff. When you set up the instrumentation and all SQL goes through SQLAlchemy, install the SQLAlchemy instrumentor alone. When the project already has both, keep them for this PR, halve the counts when you read them, and raise it as a separate change.
- [ ] **Outbound HTTP.** The client instrumentors set the full URL. The framework instrumentors alone give no outbound spans.
- [ ] **`http.route`.** The Django and FastAPI server instrumentation sets it. Check on a server span.
- [ ] **`service.name`.** `Resource.create({"service.name": "<name>"})` on the provider, or `OTEL_SERVICE_NAME`.
- [ ] **Sampling.** The SDK default is `parentbased_always_on`, which is 100%. Do not add a ratio sampler.

## Turning export on in tests

Build the provider once, in a session-scoped pytest fixture or `conftest.py`:

```python
provider = TracerProvider(resource=Resource.create({"service.name": "my-service"}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
```

- Set the endpoint and protocol by environment variable and pick the matching exporter package: `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` with the gRPC exporter, or `http://localhost:4318` with the HTTP one. When you pass `endpoint=` in code to the HTTP exporter, the value must end in `/v1/traces`.
- Instrument after the provider exists: `DjangoInstrumentor().instrument()` and `PsycopgInstrumentor().instrument()` for Django, `FastAPIInstrumentor.instrument_app(app)` and the SQLAlchemy and asyncpg instrumentors for FastAPI.
- Flush at the end of the session, in the fixture teardown: `provider.force_flush()` then `provider.shutdown()`. The provider also shuts down at interpreter exit by default, do not rely on that when `capture` is waiting.
- Scope the fixture to the session so the setup runs once.

## Test-time traps

- **No `set_tracer_provider`.** The instrumentors run, the spans go nowhere, and nothing warns.
- **Wrong engine.** The SQLAlchemy docs pass the engine object to `instrument(engine=...)`. Instrument the engine the application uses, not a second one built in the test.
- **Async SQLAlchemy not instrumented.** Passing the `AsyncEngine` itself does nothing, use `engine.sync_engine`.
- **asyncpg not instrumented.** SQLAlchemy's instrumentor does not cover a raw asyncpg call, and asyncpg needs its own `AsyncPGInstrumentor().instrument()`.
- **`opentelemetry-instrument` with several workers or a reloader.** The official troubleshooting page says a reloader (Flask debug mode, `runserver` autoreload) and pre-fork servers with several workers break zero-code instrumentation. If the tests start a real server, run it with one worker and no reloader (`manage.py runserver --noreload`, `uvicorn` without `--reload`), or keep to in-process clients.
- **Provider built in the application's lifespan.** When the app sets up OpenTelemetry and its database in a lifespan or startup hook, reuse that setup instead of building a second provider in the test. `httpx.ASGITransport` and a `TestClient` used without `with` do not run the lifespan, so enter it yourself (`async with app.router.lifespan_context(app)`, or `with TestClient(app)`). Enter it once per test process: `trace.set_tracer_provider` works only once, a second call keeps the first provider, and after the first lifespan shuts it down the later spans are dropped with a single "Overriding of current TracerProvider is not allowed" log line.
- **In-process clients.** Django's test client and FastAPI's `TestClient` run in the test process, so the provider and instrumentors from the fixture apply. A server started in a subprocess has its own interpreter and needs its own setup and environment.
- **Last batch lost.** The batch processor holds spans until its schedule or a flush. Without the final `force_flush()` the last tests vanish.
- **Parameters read as `redundant_sql`.** Drivers send placeholders. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- `perf-sentinel capture --output <file> -- pytest <new tests>` (or `python manage.py test <labels>` for Django). The exporter variables set on the `capture` command are inherited by the test process.
- With `pytest-xdist`, each worker is its own process and runs the session fixture. Run the new tests in one process, or check that every worker exports.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- OpenTelemetry Python, instrumentation and the tracer provider: https://opentelemetry.io/docs/languages/python/instrumentation/
- requests instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
- httpx instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
- aiohttp client instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_client.html
- OpenTelemetry Python, exporters: https://opentelemetry.io/docs/languages/python/exporters/
- Zero-code Python, troubleshooting (reloader, workers): https://opentelemetry.io/docs/zero-code/python/troubleshooting/
- SDK environment variables, sampler default: https://opentelemetry.io/docs/languages/sdk-configuration/general/
- OTLP exporter variables: https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/
- Python SDK trace API, `force_flush`: https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.html
- Django instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
- FastAPI instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
- psycopg instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg/psycopg.html
- SQLAlchemy instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
- asyncpg instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncpg/asyncpg.html
- Perf Sentinel, Django and psycopg: https://perf-sentinel.dev/docs/INSTRUMENTATION#python-django-5x--psycopg-otel-sdk-142
- Perf Sentinel, FastAPI, SQLAlchemy and asyncpg: https://perf-sentinel.dev/docs/INSTRUMENTATION#python-fastapi--sqlalchemy-2x--asyncpg-otel-sdk-142

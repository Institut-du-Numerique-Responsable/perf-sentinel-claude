# Ruby, Rails

Status: written from official docs, not yet tried

## Recommended instrumentation

- Library first: the OpenTelemetry Ruby SDK in an initializer. The gems are `opentelemetry-sdk`, `opentelemetry-exporter-otlp` and `opentelemetry-instrumentation-all`.
- Initializer, `config/initializers/opentelemetry.rb`. `use_all` enables every instrumentation gem in the bundle:

```ruby
require 'opentelemetry/sdk'
require 'opentelemetry/instrumentation/all'
require 'opentelemetry-exporter-otlp'

OpenTelemetry::SDK.configure do |c|
  c.service_name = '<name>'
  c.use_all
end
```
- To pick instrumentations one by one, use `c.use 'OpenTelemetry::Instrumentation::<Name>', { ...options }` (the `pg` and `mysql2` READMEs show the form).
- Check the current version of every gem on its page. Write no version number from this file.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** The driver instrumentations (`pg`, `mysql2`, `trilogy`) put the statement in `db.statement`. Their option `db_statement` takes `:obfuscate` (literals replaced by `?`, the default), `:include` (raw SQL) or `:omit` (no statement). Never `:omit`, Perf Sentinel drops a SQL span with no text. `:include` writes literal values into the spans, use it with test data only.
- [ ] **Which gem emits the SQL span.** The driver gem, or ActiveRecord, or both: unverified. The ActiveRecord README does not say what spans it creates, and the driver READMEs document the `db.statement` attribute. Check the capture: count the spans per query, and read where the text sits.
- [ ] **ORM scope.** The ActiveRecord instrumentation appears in the instrumentation scope when it emits a span. Per the Perf Sentinel page this lets findings carry ActiveRecord fixes, and only for record-loading queries. Aggregates (`count`, `sum`) may carry only the driver span.
- [ ] **Outbound HTTP.** `net_http`, `faraday`, `http` instrumentations are in the bundle. Check that client spans carry the full URL.
- [ ] **`http.route`.** The pages read do not say which instrumentation sets `http.route`. Check a server span, and without it findings group by raw path.
- [ ] **`service.name`.** `c.service_name`, or `OTEL_SERVICE_NAME`.
- [ ] **Sampling.** The SDK default is `parentbased_always_on`, which is 100%.

## Turning export on in tests

- With `opentelemetry-exporter-otlp` required, traces go to an OTLP endpoint on `localhost:4318` by default (the HTTP transport). Override with `OTEL_EXPORTER_OTLP_ENDPOINT`, for example `http://localhost:4318`.
- Set the endpoint in the environment of the test run, not in the initializer, so local and CI runs match.
- The initializer runs when Rails boots. In a Rails test run that is when `config/environment` loads, so the variables must already be set at that point.
- Flush at the end of the run: `OpenTelemetry.tracer_provider.force_flush` then `shutdown`, in `Minitest.after_run` or `RSpec.configure { |c| c.after(:suite) { ... } }`. The batch span processor also flushes at process exit, do not rely on it when `capture` is waiting.

## Test-time traps

- **Console exporter left in.** `OTEL_TRACES_EXPORTER=console` (used in the getting-started) prints spans and exports none.
- **Statement omitted.** `db_statement: :omit` leaves no text, so no SQL span reaches Perf Sentinel.
- **Last batch lost.** No `force_flush`/`shutdown`, no final spans.
- **Wrong port.** The exporter speaks HTTP. Pointed at the gRPC port 4317 it exports nothing and says nothing useful.
- **Parameters read as `redundant_sql`.** With `:obfuscate` the values are `?`. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- `perf-sentinel capture --output <file> -- bundle exec rspec <new specs>` (or `bin/rails test <files>`). The exporter variables set for `capture` are inherited by the test run.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file. The span source is unverified on this stack, so read the spans in the capture before trusting a green result.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- OpenTelemetry Ruby, getting started: https://opentelemetry.io/docs/languages/ruby/getting-started/
- OpenTelemetry Ruby, instrumentation: https://opentelemetry.io/docs/languages/ruby/instrumentation/
- OpenTelemetry Ruby, exporters: https://opentelemetry.io/docs/languages/ruby/exporters/
- `pg` instrumentation: https://github.com/open-telemetry/opentelemetry-ruby-contrib/tree/main/instrumentation/pg
- `mysql2` instrumentation: https://github.com/open-telemetry/opentelemetry-ruby-contrib/tree/main/instrumentation/mysql2
- `trilogy` instrumentation: https://github.com/open-telemetry/opentelemetry-ruby-contrib/tree/main/instrumentation/trilogy
- `active_record` instrumentation: https://github.com/open-telemetry/opentelemetry-ruby-contrib/tree/main/instrumentation/active_record
- SDK environment variables, sampler default: https://opentelemetry.io/docs/languages/sdk-configuration/general/
- Perf Sentinel, Rails and ActiveRecord: https://perf-sentinel.dev/docs/INSTRUMENTATION#ruby-rails--activerecord-opentelemetry-ruby

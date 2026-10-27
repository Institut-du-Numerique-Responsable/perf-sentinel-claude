# PHP, Laravel and Symfony

Status: written from official docs, not yet tried

## Recommended instrumentation

- Library first: the OpenTelemetry PHP extension plus the SDK and instrumentation packages from Composer, configured by environment variables. This is what opentelemetry.io calls PHP auto-instrumentation. It needs a minimum PHP version (check it on the linked page), the extension, Composer autoloading, the SDK and one or more instrumentation libraries. The extension alone generates no traces.
- Install: `pecl install opentelemetry` (or `pickle`, `PIE`, `install-php-extensions` in Docker, or a distro package), add `extension=opentelemetry.so` to `php.ini`, then `composer require open-telemetry/sdk open-telemetry/exporter-otlp`.
- Instrumentation packages: `open-telemetry/opentelemetry-auto-pdo` for SQL, and `open-telemetry/opentelemetry-auto-laravel` or `open-telemetry/opentelemetry-auto-symfony` plus `open-telemetry/opentelemetry-auto-doctrine`.
- OpenTelemetry also ships a PHP Distro (Linux packages, no Composer step). If the project already uses it, keep it for this PR and mention the Composer route as a separate migration.
- Check the current version of every package on its page. Write no version number from this file.

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text on the right span.** The PDO instrumentation creates spans for selected `PDO` and `PDOStatement` methods. With prepared statements the text may sit on the `prepare` span only. Its README adds `OTEL_PHP_INSTRUMENTATION_PDO_DISTRIBUTE_STATEMENT_TO_LINKED_SPANS=true` to copy the statement onto the `execute` and `fetchAll` spans. If the repeated `execute` spans have no text in the capture, set it.
- [ ] **Doctrine.** The Doctrine instrumentation hooks `Doctrine\DBAL\Driver` and `Connection` methods. With Symfony, install it next to `-auto-symfony`. With raw PDO and no Doctrine, `-auto-pdo` alone.
- [ ] **Which attribute carries the text.** The READMEs read do not name it, check the capture for `db.statement` or `db.query.text`.
- [ ] **Outbound HTTP.** The PSR-18, Guzzle and Curl instrumentation packages cover HTTP clients. Install the one that matches the project, check that client spans carry the full URL.
- [ ] **`http.route`, `service.name`.** `OTEL_SERVICE_NAME`. Whether the Laravel and Symfony packages set `http.route` is not on the pages read, check a server span.
- [ ] **Sampling.** The SDK default is `parentbased_always_on`, which is 100%.

## Turning export on in tests

Environment, as on the official page, with the protocol set and the port to match:

```
OTEL_PHP_AUTOLOAD_ENABLED=true
OTEL_SERVICE_NAME=<name>
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

- The official example uses `http/protobuf` on 4318. Use it for `perf-sentinel capture`.
- The same keys can go in `php.ini`.
- Set the variables in the environment of the test process, before PHP starts. Whether values from `phpunit.xml` `<env>` are applied before the SDK autoloads is unverified, so prefer the command line or the CI step.
- The extension hooks run only when the SDK autoloader is enabled (`OTEL_PHP_AUTOLOAD_ENABLED=true`).

## Test-time traps

- **Hooks under PHPUnit CLI.** Unverified: the official page documents web and CLI scripts in general, not PHPUnit. Check that spans appear for the new tests, and read the capture before trusting a green result.
- **Extension not loaded in the CLI.** The CLI can use a different `php.ini` from FPM. Check `php -m | grep opentelemetry` with the same binary that runs the tests.
- **Extension without the SDK or an instrumentation package.** No spans, no error.
- **PDO statements.** See above, the text may be missing on `execute` spans.
- **In-process HTTP kernel.** Laravel's test client and Symfony's `KernelBrowser` call the framework in the test process, so the hooks and the exporter configuration are the ones of the test run. A server started as a separate process needs the same environment.
- **Last batch lost.** The SDK exports at the end of the process. A test runner that is killed, or `exit` from a test, skips it.
- **Wrong port.** The official example is HTTP on 4318. An endpoint on 4317 with HTTP exports nothing and says nothing useful.
- **Parameters read as `redundant_sql`.** PDO templates are obfuscated by default, which is enough for detection. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).

## Running the tests under capture

- `perf-sentinel capture --output <file> -- vendor/bin/phpunit <new tests>` (or `php artisan test --filter ...`). The exporter variables set for `capture` are inherited by the test process.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, the diff's tables in the capture file. The PHPUnit hook behavior is unverified, so a green run with zero spans is a setup problem, not a clean result.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- OpenTelemetry PHP zero-code overview: https://opentelemetry.io/docs/zero-code/php/
- PHP auto-instrumentation, install and configuration: https://opentelemetry.io/docs/zero-code/php/auto/
- PDO instrumentation: https://github.com/open-telemetry/opentelemetry-php-contrib/tree/main/src/Instrumentation/PDO
- Doctrine instrumentation: https://github.com/open-telemetry/opentelemetry-php-contrib/tree/main/src/Instrumentation/Doctrine
- Laravel instrumentation: https://github.com/open-telemetry/opentelemetry-php-contrib/tree/main/src/Instrumentation/Laravel
- Symfony instrumentation: https://github.com/open-telemetry/opentelemetry-php-contrib/tree/main/src/Instrumentation/Symfony
- SDK environment variables, sampler default: https://opentelemetry.io/docs/languages/sdk-configuration/general/
- Perf Sentinel, Laravel, Symfony and PHP: https://perf-sentinel.dev/docs/INSTRUMENTATION#php-laravel--eloquent-symfony--doctrine-opentelemetry-php

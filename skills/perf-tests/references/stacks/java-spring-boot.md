# Java, Spring Boot

Status: written from official docs, not yet tried

## Recommended instrumentation

Check the Spring Boot major version in the build file first, then the current version of every artifact on its official page. Write no version number from this file.

**Spring Boot 4**

- Library first: `spring-boot-starter-opentelemetry`. The Spring team calls it its preferred option. It creates spans through Micrometer Observation and exports them over OTLP, with no bytecode instrumentation.
- opentelemetry.io treats the Java agent as the default choice and the Spring starter as the fallback (native images, startup cost, another agent). Both paths are legitimate, link both when you propose one.
- If the project already runs the agent, keep it for this PR and mention the starter as a separate migration.
- The starter traces less than the agent: add what the next section lists.

**Spring Boot 3**

- No Spring starter. Use the agent first, or the Micrometer bridge (`micrometer-tracing-bridge-otel`) with `opentelemetry-exporter-otlp`, configured with `management.otlp.tracing.*`.
- JDBC spans on the bridge path come from Datasource Micrometer too, check that its line matches Spring Boot 3.

**Never run both** the agent and the starter or bridge in one JVM, spans come out twice. Where the agent runs, set `management.tracing.export.enabled=false` (Boot 4) or `management.tracing.enabled=false` (Boot 3).

## What must reach the spans

Contract and attribute list: [perf-sentinel.md](../perf-sentinel.md), section `What makes a span usable`.

- [ ] **SQL text.** The agent emits it from JDBC (`db.statement` by default, `db.query.text` with `otel.semconv-stability.opt-in=database`, Perf Sentinel reads both). The Spring starter does not instrument JDBC: add `net.ttddyy.observation:datasource-micrometer-spring-boot` and `datasource-micrometer-opentelemetry`, same version for both, and set `jdbc.includes=QUERY` (the docs write the value in upper case) for one span per statement. Without the OpenTelemetry module the statement lands in a `jdbc.query[0]` tag Perf Sentinel does not read.
- [ ] **Outbound HTTP.** The agent traces any client. With the starter, build every `RestClient`, `RestTemplate` and `WebClient` from the injected `RestClient.Builder`, `RestTemplateBuilder` or `WebClient.Builder`. A client from a static factory has no span.
- [ ] **`http.route`.** The starter's default server span carries the raw path, so each id becomes its own endpoint. Declare an `OpenTelemetryServerRequestObservationConvention` bean (Spring Framework) or extend `DefaultServerRequestObservationConvention` and add `http.route` as a high-cardinality key. The agent sets it.
- [ ] **`service.name`.** `spring.application.name` for the starter, `OTEL_SERVICE_NAME` for the agent.
- [ ] **Threads.** A query joins a trace only if an observation is current on its thread. For `@Async`, set `spring.task.execution.propagate-context=true` on the auto-configured executor, or register a `ContextPropagatingTaskDecorator` bean on your own executor.
- [ ] **Sampling 100%.** `management.tracing.sampling.probability=1.0` (the default is 0.1). The agent takes `OTEL_TRACES_SAMPLER=always_on`.
- [ ] **Messaging.** Off by default with the starter. The observation switches are `spring.kafka.template.observation-enabled`, `spring.rabbitmq.template.observation-enabled` and their listener twins (all default to false).

## Turning export on in tests

Starter (Boot 4):

```properties
management.opentelemetry.tracing.export.otlp.endpoint=http://localhost:4318/v1/traces
management.tracing.sampling.probability=1.0
management.tracing.export.otlp.enabled=true
```

- The endpoint has no default. Without it spans never leave the JVM. The transport is HTTP, so port 4318 and the `/v1/traces` path.
- Put the properties in the Failsafe `<systemPropertyVariables>` or the Gradle `Test` task `systemProperty`, or in a test properties file. Do not hardcode a port the capture may not get.
- With no listener the export fails in the background without failing a test, so the configuration can stay in the build.
- `OTEL_*` variables: Spring Boot maps only a subset, and which subset depends on the release. Prefer the properties.

Agent (Boot 3, or a project that already uses it):

- Maven: copy the agent jar with `maven-dependency-plugin` (`copy` goal, `pre-integration-test` phase) and append `-javaagent:${project.build.directory}/opentelemetry-javaagent.jar` to the existing Failsafe `<argLine>`, after `@{argLine}` so JaCoCo keeps working. Never overwrite the `argLine`. Gradle: `jvmArgs` on the `Test` task.
- Set `OTEL_TRACES_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and an explicit `OTEL_EXPORTER_OTLP_PROTOCOL`. The agent defaults to `http/protobuf` since 2.0, so `http/protobuf` means port 4318 and `grpc` port 4317. Add `OTEL_TRACES_SAMPLER=always_on`, `OTEL_SERVICE_NAME`, and `OTEL_METRICS_EXPORTER=none`, `OTEL_LOGS_EXPORTER=none`.
- Use real environment variables or system properties. The agent starts before Spring, so `application.properties` never reaches it.
- Pin the agent version to what the project's Dockerfile or CI uses, if any.

## Test-time traps

- **`@SpringBootTest` turns export off.** Spring Boot's docs say tracing components that report data are not auto-configured there. In Boot 4 the switch is a context customizer in `spring-boot-micrometer-tracing-test` that sets `management.tracing.export.enabled=false` when that module is on the test classpath. Fix, any one of: `@AutoConfigureTracing` on the test, `spring.test.tracing.export=true`, or `management.tracing.export.otlp.enabled=true`. In Boot 3 the annotation is `@AutoConfigureObservability`.
- **Sliced tests never export** (`@WebMvcTest`, `@DataJpaTest`). Use `@SpringBootTest` for the scenario.
- **Forked test JVM, no stdout.** Surefire and Failsafe use the fork's stdout as their command channel, so a stdout span exporter is diverted to a `.dumpstream` file. Send OTLP to `perf-sentinel capture` instead.
- **`mvn clean` deletes the capture file** when it sits under `target/`. Write it elsewhere or leave `clean` out of the wrapped command.
- **Injected builders only.** A client built with `RestClient.builder()` is invisible, and so is every call it makes.
- **`jdbc.includes` left at its default** adds connection and fetch spans on top of the statements. Set it to `QUERY`.
- **Parameters read as `redundant_sql`.** Datasource Micrometer sanitizes literals and Hibernate binds `?`, so a looped query can read as `redundant_sql`. See `Sanitized SQL and the reclassification` in [perf-sentinel.md](../perf-sentinel.md).
- **A lazy-loading N+1 has no ORM scope, even with the agent.** The agent's SQL spans carry the `io.opentelemetry.jdbc` scope. Perf Sentinel also reads the scopes of their parents, so a repository method called in a loop reads as `n_plus_one_sql` (its `spring-data` span is the parent). A lazy collection loaded in a loop has no such parent: each `SELECT` sits directly under the server span, and `auto` falls back on the timing spread alone. Measured on one run: 15 loads read as a critical `n_plus_one_sql` (spread 0.56, just over 0.5), 150 loads as a `redundant_sql` warning. Count either as the N+1, and expect the 15-load case to flip between runs. For a stable classification in CI, propose `sanitizer_aware_classification = "strict"`, which reclassifies from 15 identical queries.

## Running the tests under capture

- Maven: `perf-sentinel capture --output <file outside target/> -- mvn verify`. Gradle: wrap `./gradlew integrationTest` (or the project's task) the same way.
- A starter export is batched: use a longer `--grace-ms` than the default, for example 3000, so the last test's spans flush.
- Starter, HTTP/protobuf: endpoint `http://localhost:4318/v1/traces`. Agent: match `OTEL_EXPORTER_OTLP_PROTOCOL` and the port.
- Then the trace check from `Local run` in the skill: `analysis.events_processed` above zero, and the diff's tables in the capture file. A starter project without Datasource Micrometer gives zero SQL spans and zero findings.
- Flags, exit codes and the check: [perf-sentinel.md](../perf-sentinel.md), section `Commands`.

## Links

- Spring Boot tracing: https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- Spring Boot observability, JDBC and context propagation: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Spring Boot tracing in tests: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot properties: https://docs.spring.io/spring-boot/appendix/application-properties/index.html
- Spring blog, OpenTelemetry with Spring Boot: https://spring.io/blog/2025/11/18/opentelemetry-with-spring-boot
- Datasource Micrometer: https://jdbc-observations.github.io/datasource-micrometer/docs/current/docs/html/
- OpenTelemetry, Spring Boot starter versus agent: https://opentelemetry.io/docs/zero-code/java/spring-boot-starter/
- OpenTelemetry Java agent: https://opentelemetry.io/docs/zero-code/java/agent/
- OpenTelemetry Java agent configuration: https://opentelemetry.io/docs/zero-code/java/agent/configuration/
- OTLP exporter variables: https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/
- Surefire, `@{argLine}` and the corrupted channel: https://maven.apache.org/surefire/maven-surefire-plugin/faq.html
- Perf Sentinel, Spring Boot 4 starter: https://perf-sentinel.dev/docs/INSTRUMENTATION#java-spring-boot-4-starter-spring-boot-starter-opentelemetry
- Perf Sentinel, starter integration tests: https://perf-sentinel.dev/docs/INSTRUMENTATION#7-integration-tests
- Perf Sentinel, Java agent: https://perf-sentinel.dev/docs/INSTRUMENTATION#java-opentelemetry-java-agent-v227-spring-boot-helidon-4x
- Perf Sentinel, Failsafe CI: https://perf-sentinel.dev/docs/INSTRUMENTATION#ci-integration-tests-maven-failsafe
- Perf Sentinel, capture option: https://perf-sentinel.dev/docs/INSTRUMENTATION#option-1-perf-sentinel-capture-recommended

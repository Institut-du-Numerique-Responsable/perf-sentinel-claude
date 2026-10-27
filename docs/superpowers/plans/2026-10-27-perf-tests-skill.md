# `perf-tests` skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `perf-sentinel` Claude plugin with its first skill, `perf-tests`, which writes production-shaped performance integration tests for a change, runs them under `perf-sentinel capture`, and wires Perf Sentinel into the team's CI.

**Architecture:** The skill is prose, not code: a `SKILL.md` that carries the §5 flow of the spec, plus reference files loaded on demand (one per stack, one per CI, one for Perf Sentinel itself, one for fix safety). A stdlib Python checker enforces the structural rules the spec sets (portable frontmatter, size, doc sources, status markers). Behavior is measured two ways: `claude plugin eval` for triggering, and end-to-end trials on real services for the flow.

**Tech Stack:** Claude Code plugin format (`.claude-plugin/plugin.json`, `marketplace.json`, `skills/`), `claude plugin validate --strict`, `claude plugin eval`, Python 3 stdlib (`unittest`), GitHub Actions. Trials use the `perf-sentinel` binary, Docker, .NET, Python and a Spring Boot 4 service.

**Spec:** `docs/superpowers/specs/2026-10-27-perf-tests-skill-design.md`. Research behind it: `docs/research/` (local only, excluded from git; the facts this plan needs are copied below).

## Global Constraints

- Generic: no company name, internal path, internal library or team convention anywhere in `skills/`, `evals/`, `README.md`. The enterprise trial service is never named.
- Stacks covered in v1, one reference each: Java (Spring Boot, Quarkus, Micronaut), C# (.NET, EF Core), Python (Django, FastAPI), Go (GORM), Node.js (NestJS, Prisma), Rust (Diesel, SeaORM), Ruby (Rails), PHP (Laravel, Symfony).
- CIs covered in v1, one reference each: GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, plus `other.md` for unknown internal layers (describe the result to obtain, never invent the layer's API).
- Doc sources, in this order: opentelemetry.io and the framework's official docs, then `https://perf-sentinel.dev/docs/...`. Never link to `github.com/Institut-du-Numerique-Responsable/perf-sentinel/blob/` or `/tree/`. Release download URLs (`/releases/`) are allowed.
- No pinned version numbers in references: give the rule and the link, and tell the agent to check the current version at write time. A version may appear only as a historical breakpoint ("removed in", "before").
- Library or starter first, agent second (spec §3). If the project already uses an agent, keep it for this PR and mention the starter as a separate migration.
- Nothing that touches the repo, the machine or the CI happens without the developer's yes.
- In CI, only what Perf Sentinel already has: `capture` around the existing test step, `analyze` (SARIF, JSON, HTML archived), `.perf-sentinel-acknowledgments.toml` as the register of unresolved findings, `analyze --ci` gate left to the team. The Hub is never fed by CI.
- Skill frontmatter: only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. `description` ≤ 1024 characters, key use case first. `SKILL.md` < 500 lines.
- Skill and references in English. The skill answers in the developer's language.
- Plugin name `perf-sentinel`, skill name `perf-tests`, command `/perf-sentinel:perf-tests [free-text precision]`. Marketplace in the same repo with `"source": "./"`, entry name `perf-sentinel`.
- License: `AGPL-3.0-only`, same as Perf Sentinel (confirm with Robin before the first release tag).
- Every stack and CI reference starts with exactly one status line: `Status: tried end-to-end` or `Status: written from official docs, not yet tried`. Untried ones make the skill more careful (check current docs before acting, insist on the trace check of §5.7).

## Review Focus

1. **A repo with no integration tests at all.** Expected: the skill says there is no style to copy, proposes the framework's idiomatic minimal harness (and a real DB container if Docker is available), and asks before creating it. Pinned by eval case `no-integration-tests` (Task 2) and the rule in `SKILL.md` §"Recon" (Task 3).
2. **OTLP ports 4317/4318 already taken locally** (a dev collector or a running daemon). Expected: `capture` exits 1, the skill reports it and reruns with `--listen-port-grpc`/`--listen-port-http` plus the matching exporter endpoint, not silently skipping the local run. Pinned by a check in Task 9.
3. **Application under test runs inside a container** (Testcontainers app container, docker compose). Expected: `capture --listen-address 0.0.0.0` and an exporter endpoint on `host.docker.internal`. Pinned in `references/perf-sentinel.md` (Task 4) and a check in Task 10.
4. **Sanitized SQL classed as `redundant_sql` instead of `n_plus_one_sql`** (EF Core `@__param_0`, SqlClient `?`, bare drivers with no ORM scope). Expected: the skill counts `redundant_sql` on the looped template as the N+1 it wrote the test for, and on bare drivers uses ≥ 15 iterations. Pinned in `references/perf-sentinel.md` (Task 4) and asserted in Task 9.
5. **A diff spanning two services or two stacks** (monorepo). Expected: one scenario list per service, each with its own stack reference and its own capture run. Pinned by eval case `monorepo-two-stacks` (Task 2).

---

## File Structure

```
.claude-plugin/plugin.json             manifest: name, displayName, description, author, license, homepage, repository (no version: git SHA pins)
.claude-plugin/marketplace.json        one entry, "source": "./"
skills/perf-tests/SKILL.md             the §5 flow, consent rule at the top, map of references
skills/perf-tests/references/perf-sentinel.md   detectors and their trigger shapes, gate defaults, CLI, exit codes, ack entry format, site links
skills/perf-tests/references/fix-safety.md      §5.9 non-regression checklist (reused later by piece 2)
skills/perf-tests/references/stacks/{java-spring-boot,java-quarkus,java-micronaut,dotnet,python,go,node,rust,ruby,php}.md
skills/perf-tests/references/ci/{github-actions,gitlab-ci,jenkins,azure-devops,circleci,other}.md
evals/<case>/case.yaml                 trigger and behavior cases for `claude plugin eval`
scripts/check_plugin.py                structural rules (stdlib only)
scripts/test_check_plugin.py           unittest for the checker
.github/workflows/ci.yml               checker tests, checker, `claude plugin validate --strict`
README.md, LICENSE, CHANGELOG.md
```

No `scripts/` inside the skill in v1: no script has yet proven it avoids a real error (spec §6). Add one only if a trial in Tasks 9-11 shows the agent repeatedly getting a mechanical step wrong.

---

### Task 1: Plugin scaffold and structural checker

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `README.md`, `LICENSE`, `CHANGELOG.md`, `.gitignore`
- Create: `scripts/check_plugin.py`, `scripts/test_check_plugin.py`, `.github/workflows/ci.yml`
- Create: `skills/perf-tests/SKILL.md` (frontmatter + one-line placeholder body, filled in Task 3)

**Interfaces:**
- Produces: `python3 scripts/check_plugin.py [root]` exits 0 when clean, 1 with one `path: rule: detail` line per violation. Rules, by id:
  - `skill-size`: `SKILL.md` has fewer than 500 lines.
  - `frontmatter-keys`: top-level frontmatter keys ⊆ the six portable ones.
  - `description-length`: `description` ≤ 1024 characters.
  - `name-matches-dir`: `name` equals the skill directory name.
  - `doc-source`: no `github.com/Institut-du-Numerique-Responsable/perf-sentinel/blob/` or `/tree/` under `skills/`.
  - `status-line`: every `references/stacks/*.md` and `references/ci/*.md` has, as its first non-heading line, one of the two exact status strings.
  - `stack-sections`: every `references/stacks/*.md` has the `##` headings `Recommended instrumentation`, `What must reach the spans`, `Turning export on in tests`, `Test-time traps`, `Running the tests under capture`, `Links`.
  - `ci-sections`: every `references/ci/*.md` has `Detecting it`, `Wrapping the test step`, `Analyze and archive`, `Showing results in the PR`, `Optional gate`, `Links`.
- Produces: `.gitignore` contains `evals/results/`.

- [ ] **Step 1: Write the failing tests** in `scripts/test_check_plugin.py`

Each test builds a minimal valid plugin tree in a `tempfile.TemporaryDirectory`, breaks one rule, and asserts `check(root)` returns exactly that rule id:

```python
def test_clean_tree_passes(self):        self.assertEqual(check(self.root), [])
def test_skill_over_500_lines(self):     ...; self.assertEqual(rule_ids(check(self.root)), ["skill-size"])
def test_non_portable_key(self):         # add "argument-hint: x" -> ["frontmatter-keys"]
def test_description_too_long(self):     # 1025 chars -> ["description-length"]
def test_name_differs_from_dir(self):    # name: perf-test -> ["name-matches-dir"]
def test_github_blob_link(self):         # .../perf-sentinel/blob/main/docs/CI.md -> ["doc-source"]
def test_release_link_allowed(self):     # .../perf-sentinel/releases/latest -> []
def test_missing_status_line(self):      # stacks/go.md without status -> ["status-line"]
def test_missing_stack_section(self):    # drop "## Test-time traps" -> ["stack-sections"]
def test_missing_ci_section(self):       # drop "## Optional gate" -> ["ci-sections"]
```

`check(root: Path) -> list[Violation]`, `Violation = namedtuple("Violation", "path rule detail")`, `rule_ids(vs) -> list[str]` sorted.

- [ ] **Step 2: Run them, expect failure**

Run: `python3 -m unittest scripts/test_check_plugin.py -v`
Expected: `ModuleNotFoundError: No module named 'check_plugin'` (or ImportError).

- [ ] **Step 3: Implement `check(root: Path) -> list[Violation]` and `main()` in `scripts/check_plugin.py`**

Frontmatter: text between the first line `---` and the next `---`; top-level keys are lines matching `^([a-z][a-z-]*):`; `description` value is the rest of its line plus following indented lines (handles `description: |`). No YAML dependency.

- [ ] **Step 4: Run tests, expect pass**

Run: `python3 -m unittest scripts/test_check_plugin.py -v`
Expected: 10 tests, `OK`.

- [ ] **Step 5: Write manifests and repo files**

- `plugin.json`: `name: "perf-sentinel"`, `displayName: "Perf Sentinel"`, `description` (one sentence: performance integration tests that surface N+1, redundant and slow I/O before production), `author: {name: "Robin Trassard", url: "https://github.com/robintra"}`, `license: "AGPL-3.0-only"`, `homepage: "https://perf-sentinel.dev"`, `repository: "https://github.com/robintra/perf-sentinel-claude-plugin"`, `keywords`. No `version`.
- `marketplace.json`: `name: "perf-sentinel"`, `owner: {name: "Robin Trassard"}`, `plugins: [{name: "perf-sentinel", source: "./"}]`.
- `SKILL.md` frontmatter: `name: perf-tests`, `license: AGPL-3.0-only`, `compatibility` (needs a repo checkout, Docker for DB-backed tests, the `perf-sentinel` binary or permission to install it), `metadata: {author: "...", repository: "..."}`, `allowed-tools: Bash(git diff *) Bash(git log *) Bash(git merge-base *) Bash(perf-sentinel --version) Bash(perf-sentinel analyze *) Bash(perf-sentinel inspect *)`, `description: Writes performance integration tests for the current change and runs them under Perf Sentinel.` (provisional, Task 3 rewrites it).
- `README.md`: what the plugin does (3 lines), install (`/plugin marketplace add robintra/perf-sentinel-claude-plugin` then `/plugin install perf-sentinel@perf-sentinel`), usage (`/perf-sentinel:perf-tests [precision]`), link to https://perf-sentinel.dev, license.
- `CHANGELOG.md`: Keep a Changelog layout, `## [Unreleased]`.
- `LICENSE`: AGPL-3.0 text copied from the perf-sentinel repo's `LICENSE`.

- [ ] **Step 6: Run the checker and the validator**

Run: `python3 scripts/check_plugin.py . && claude plugin validate --strict .`
Expected: both exit 0.

- [ ] **Step 7: CI workflow** `.github/workflows/ci.yml` on `push` and `pull_request`: checkout, `python3 -m unittest scripts/test_check_plugin.py`, `python3 scripts/check_plugin.py .`, then `npm install -g @anthropic-ai/claude-code` and `claude plugin validate --strict .`. If the validate step needs credentials in CI, drop it from the workflow and add it to the release checklist in Task 12 instead.

- [ ] **Step 8: Commit**

```bash
git add .claude-plugin skills scripts .github README.md LICENSE CHANGELOG.md .gitignore
git commit -m "feat: scaffold the perf-sentinel plugin and its structural checker"
```

---

### Task 2: Trigger and behavior evals (red)

**Files:**
- Create: `evals/<case>/case.yaml` for each case below (start each with `claude plugin eval init --bare <case>` and fill the template)

**Interfaces:**
- Consumes: the plugin from Task 1.
- Produces: `claude plugin eval . --threshold 0.67` as the trigger gate used by Tasks 3 and 12.

Cases (`runs: 3`). `tool_used: Skill` graders are with-only indicators under the default ablation; the LLM graders carry the score:

| Case | Prompt (gist) | Graders |
|---|---|---|
| `explicit-command` | `/perf-sentinel:perf-tests PROJ-1234` in a scaffold repo with a diff touching a repository class | `tool_used: Skill`; LLM: first reply does recon only, modifies no file, ends with questions or a scenario list |
| `suggest-after-db-feature` | "I'm done with the feature that loads a client's contracts, can you review it?" (diff touches SQL) | LLM: proposes `/perf-sentinel:perf-tests` in one line; does not write tests or edit files without a yes |
| `no-suggest-ui-only` | same wording, diff touches only CSS/templates | LLM: does not propose the skill |
| `no-trigger-typo` | "fix the typo in README" | `tool_used: Skill` must be absent |
| `load-test-out-of-scope` | "write a k6 load test for /orders with 500 users" | LLM: does not start the skill's flow; if the skill is mentioned, it says it judges one trace at a time and points to a load-testing tool |
| `no-integration-tests` | explicit command in a scaffold repo with unit tests only | LLM: says there is no IT style to copy and asks before creating a harness (Review Focus 1) |
| `monorepo-two-stacks` | explicit command, diff touches a Spring Boot service and a FastAPI service | LLM: one scenario list per service, each naming its stack (Review Focus 5) |

Scaffold repos are tiny fixtures under `evals/<case>/fixture/` (a few files and a prepared git history), set up by the case's `scaffold_script`.

- [ ] **Step 1: Write the seven cases and their fixtures**
- [ ] **Step 2: Run, expect failure**

Run: `claude plugin eval . --scaffold --trust-plugin --threshold 0.67`
Expected: exit 1; `explicit-command` and `suggest-after-db-feature` fail (the placeholder skill does nothing useful), negative cases may already pass.

- [ ] **Step 3: Commit**

```bash
git add evals
git commit -m "test: add trigger and behavior evals for perf-tests"
```

---

### Task 3: `SKILL.md` and `fix-safety.md`

**Files:**
- Modify: `skills/perf-tests/SKILL.md`
- Create: `skills/perf-tests/references/fix-safety.md`

**Interfaces:**
- Consumes: reference file paths from the File Structure (Tasks 4-8 fill them; `SKILL.md` already points to them).
- Produces: the section names other files cite: `Recon`, `Change scope`, `Business context`, `Scenarios`, `Instrumentation`, `Writing the tests`, `Local run`, `Bugfix before/after`, `Fixes`, `CI wiring`, `Summary`.

- [ ] **Step 1: Description.** ≤ 1024 characters, use case first. It must say: writes performance integration tests for the current change and runs them under Perf Sentinel; use when the user runs `/perf-sentinel:perf-tests`, or propose it in one line (never start it) when the user says a feature or bugfix is done or asks for a review and the diff touches a database, an outbound HTTP/RPC call or a message publisher; not for load tests.

- [ ] **Step 2: Body, top first** (compaction keeps the start). Order and fixed content:
  1. **Consent rule**, first paragraph: if the user did not invoke the command or say yes to a proposal, propose in one line and stop. Recon is read-only; every step that writes files, installs, runs containers or touches CI asks first.
  2. **Arguments**: `$ARGUMENTS` is a free-text precision (ticket ref, feature name). If it looks like a ticket and a ticket tool is available, read it.
  3. One `##` section per spec §5.1-5.11 with the names listed under Interfaces, each a tight checklist of the spec's bullets. Pinned details: the business questions of §5.3 verbatim (feature and bugfix lists); the scenario example format of §5.4; Perf Sentinel minimums as a floor (5 occurrences, 10 for critical); the one-minute local duration warning of §5.6; the trace check of §5.7 (non-empty, has SQL/HTTP spans, has the diff's queries or calls, otherwise the test is wrong); capture output outside the build directory; the before/after worktree run of §5.8 with its best-effort fallback; the acknowledgment entry always with `expires_at`; in `Business context` and `Fixes`, if a Perf Sentinel Hub MCP tool is available, read production findings for the touched endpoints, and work the same without it (spec §8).
  4. **Untried references**: when the stack or CI reference says `written from official docs, not yet tried`, fetch the linked official page before acting and do the trace check even if the run looks green.
  5. **Reference map**: one line per reference file saying when to load it.
- [ ] **Step 3: `fix-safety.md`**: the §5.9 checklist as three lists (Before, After, Decision), each trap named with the stack-neutral check that catches it (fetch-join duplicates or broken pagination, batch loading changing order, stale cache, transaction boundary or lazy loading breaking another caller, data loaded for nothing on another path). End with: uncovered callers are reported, never assumed correct.
- [ ] **Step 4: Run the gates**

Run: `python3 scripts/check_plugin.py . && claude plugin validate --strict . && claude plugin eval . --scaffold --trust-plugin --threshold 0.67`
Expected: all exit 0. If an eval case fails, change the description or the consent paragraph, not the case.

- [ ] **Step 5: Commit**

```bash
git add skills/perf-tests
git commit -m "feat: write the perf-tests skill flow and the fix safety checklist"
```

---

### Task 4: `references/perf-sentinel.md`

**Files:**
- Create: `skills/perf-tests/references/perf-sentinel.md`

Content pinned by this plan (from the Perf Sentinel docs, checked 2026-10-27; the file links each fact to its page instead of quoting versions):

- **What makes a span usable**: SQL needs `db.query.text` or `db.statement` (a non-SQL `db.system` is dropped); HTTP needs `url.full` or `http.url` on a non-SERVER span; RPC needs `rpc.system` + `rpc.service`/`rpc.method` on CLIENT; messaging needs `messaging.system` + destination on PRODUCER. Unusable spans are dropped silently: a thin report can mean no problem or no instrumentation. Enrichers: `service.name` (resource), `http.route`, `code.*`, `parent_span_id` (fanout, serialized).
- **Detector table** (default thresholds, per trace): the 9 rows of research table §1, including the sanitized-SQL reclassification (`auto` mode needs an ORM scope or duration spread; `strict` needs ≥ 15) and the `redundant_sql` cases for EF Core, Hibernate `?1`, gRPC and redacted .NET query strings (Review Focus 4).
- **Gate defaults**: `n_plus_one_sql_critical_max = 0`, `n_plus_one_http_warning_max = 3`, `n_plus_one_messaging_warning_max = 3`, `io_waste_ratio_max = 0.30`, `min_usable_span_ratio` unset (suggest enabling it; batch only, worst kind counts, kinds under 20 spans not judged). Always read `.perf-sentinel.toml` first; defaults only when absent.
- **Commands**: `perf-sentinel capture --output <file outside the build dir> [--grace-ms N] [--listen-address 0.0.0.0] [--listen-port-grpc P] [--listen-port-http P] -- <test command>`; background form `capture --output f &` … `kill -TERM $pid && wait`; `perf-sentinel analyze --input <file> [--config .perf-sentinel.toml] [--format json|sarif] [--ci]`; `perf-sentinel inspect --input <file>`; `perf-sentinel diff --before … --after …`. App side: `OTEL_EXPORTER_OTLP_ENDPOINT` plus an explicit `OTEL_EXPORTER_OTLP_PROTOCOL` (`grpc` → 4317, `http/protobuf` → 4318). Containers: `--listen-address 0.0.0.0` and `host.docker.internal` (Review Focus 3). Port taken: `capture` exits 1, rerun on free ports and move the exporter endpoint (Review Focus 2). Sampling 100%.
- **Exit codes**: analyze `0` pass, `1` gate failed (`--ci` only), `2` usage, `75` tooling error (missing/empty/malformed input); capture `0`, the wrapped command's own code, `1` capture failed, `2` incomplete file.
- **Acknowledgment entry template**: `[[acknowledged]]` with `signature`, `acknowledged_by` (left for the developer), `acknowledged_at` (today), `reason`, `expires_at` (always set by the skill), `service`, `source_endpoint`. Signature from `analyze --format json | jq '.findings[].signature'`. `unmatched_acknowledgment` means the entry can be removed.
- **Install**: official GitHub release asset with its SHA256 check, never a third-party mirror.
- **Links**: `https://perf-sentinel.dev/docs/INSTRUMENTATION#required-span-attributes`, `#sql-placeholder-styles-and-detection`, `#sampling-and-filtering`, `/docs/CI#exit-codes`, `/docs/CI#ci-integration-recipes`, `/docs/CLI#capture`, `/docs/CONFIGURATION#thresholds`, `/docs/ACKNOWLEDGMENTS`, `/docs/design/04-DETECTION`, `/docs/LIMITATIONS#orm-bind-parameters-and-n1-vs-redundant-classification`, `/docs/INTEGRATION#events-received-but-no-findings`.

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Check every link resolves**

Run: `grep -o 'https://perf-sentinel.dev/docs/[^ )]*' skills/perf-tests/references/perf-sentinel.md | sort -u | while read u; do printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "${u%%#*}")" "$u"; done`
Expected: every line starts with `200`. Then open each anchor once in a browser or `curl -s <page> | grep -c 'id="<anchor>"'` to confirm it exists.

- [ ] **Step 3: Run the checker** (`python3 scripts/check_plugin.py .`, expect exit 0) and commit

```bash
git add skills/perf-tests/references/perf-sentinel.md
git commit -m "docs(skill): add the Perf Sentinel reference for perf-tests"
```

---

### Task 5: JVM stack references

**Files:**
- Create: `skills/perf-tests/references/stacks/java-spring-boot.md`, `java-quarkus.md`, `java-micronaut.md`

All three start `Status: written from official docs, not yet tried` (Spring Boot flips in Task 11). Facts to carry (verify each against the linked page at write time, write no version numbers):

- **Spring Boot 4**: `spring-boot-starter-opentelemetry` first (Spring's preferred option); opentelemetry.io defaults to the agent: present both, link both. JDBC needs Datasource Micrometer (`datasource-micrometer-spring-boot` + `datasource-micrometer-opentelemetry`) with `jdbc.includes=QUERY`. Sampling `management.tracing.sampling.probability=1.0` (default 0.1). Endpoint `management.opentelemetry.tracing.export.otlp.endpoint=http://<host>:4318/v1/traces` (no default). Test trap: `@SpringBootTest` disables export only when `spring-boot-micrometer-tracing-test` is on the test classpath (`management.tracing.export.enabled=false`); fix with `@AutoConfigureTracing`, `spring.test.tracing.export=true`, or `management.tracing.export.otlp.enabled=true`. Clients from the injected `RestClient.Builder`; server convention for `http.route`; `@Async` context propagation. **Spring Boot 3**: no starter, agent first (or Micrometer bridge + OTLP exporter). Agent in Failsafe: copy with `maven-dependency-plugin`, append to `<argLine>@{argLine} -javaagent:…` (keeps JaCoCo). Forked Maven JVM cannot write traces to stdout: use `capture`. `mvn clean` deletes a capture file under `target/`. Perf Sentinel anchors: `#java-spring-boot-4-starter-spring-boot-starter-opentelemetry`, `#7-integration-tests`, `#java-opentelemetry-java-agent-v227-spring-boot-helidon-4x`, `#ci-integration-tests-maven-failsafe`, `#option-1-perf-sentinel-capture-recommended`.
- **Quarkus**: `quarkus-opentelemetry` extension, `quarkus.datasource.jdbc.telemetry=true`, `quarkus.otel.exporter.otlp.endpoint` (default gRPC 4317). Official page has no testing section: say so. Anchor `#java-quarkus-333-lts--quarkus-opentelemetry--otel-agent-v227`.
- **Micronaut**: `micronaut-tracing-opentelemetry-http` and `…-opentelemetry-jdbc`; `otel.traces.exporter` defaults to `none`, set `otlp` for tests. No Perf Sentinel section: link the official guide only.

- [ ] **Step 1: Write the three files with the six stack sections**
- [ ] **Step 2: Run** `python3 scripts/check_plugin.py .` (expect exit 0), then run the link check of Task 4 Step 2 on these files plus every non-perf-sentinel URL (`curl -s -o /dev/null -w '%{http_code}' -L`, expect `200`).
- [ ] **Step 3: Commit** `docs(skill): add the JVM stack references`

---

### Task 6: .NET and Python references

**Files:**
- Create: `skills/perf-tests/references/stacks/dotnet.md`, `python.md`

Both `not yet tried` (flip in Tasks 9 and 10).

- **.NET**: SDK configured in code is Microsoft's recommended path; auto-instrumentation is the fallback. `OpenTelemetry.Extensions.Hosting`, `.Instrumentation.AspNetCore`, `.Instrumentation.Http`, `.Exporter.OpenTelemetryProtocol`; SQL via `.Instrumentation.SqlClient` (stable, `db.query.text`), `.Instrumentation.EntityFrameworkCore` (prerelease; `db.statement` by default, `db.query.text` with `OTEL_SEMCONV_STABILITY_OPT_IN=database`), or `Npgsql.OpenTelemetry` (`.AddNpgsql()`). Call them with no options: `SetDbStatementForText` was removed (SqlClient 1.12.0-beta.3, EF Core 1.13.0-beta.1) and text is now always captured, sanitized. SqlClient stored procedures carry `db.stored_procedure.name`, not text. `OTEL_DOTNET_EXPERIMENTAL_HTTPCLIENT_DISABLE_URL_QUERY_REDACTION=true` for HTTP N+1. Tests: `WebApplicationFactory` with the OTLP endpoint env var; the in-memory exporter does not reach Perf Sentinel. EF Core N+1 often reads as `redundant_sql`. Anchor `#net-aspnet-core--entity-framework-core--opentelemetry-sdk-115`.
- **Python**: Django (psycopg instrumentor for SQL) and FastAPI (`FastAPIInstrumentor` + `SQLAlchemyInstrumentor`). Must call `trace.set_tracer_provider(provider)` before any `instrument()` (or pass `tracer_provider=`); async SQLAlchemy needs `engine=engine.sync_engine`; asyncpg needs `AsyncPGInstrumentor().instrument()`. Zero-code `opentelemetry-instrument` breaks with several workers or a reloader. In pytest, programmatic instrumentors with an OTLP exporter; force flush or shut the provider down at session end so the last batch reaches `capture`. Anchors `#python-django-5x--psycopg-otel-sdk-142`, `#python-fastapi--sqlalchemy-2x--asyncpg-otel-sdk-142`.

- [ ] **Step 1: Write both files**
- [ ] **Step 2: Checker and link check** as in Task 5 Step 2
- [ ] **Step 3: Commit** `docs(skill): add the .NET and Python stack references`

---

### Task 7: Go, Node.js, Rust, Ruby, PHP references

**Files:**
- Create: `skills/perf-tests/references/stacks/go.md`, `node.md`, `rust.md`, `ruby.md`, `php.md`

All `not yet tried`.

- **Go**: libraries (zero-code options are work in progress): `otelhttp` for server and client transport, `otelsql` for `database/sql`, `otelpgx` for pgx, GORM plugin `gorm.io/plugin/opentelemetry/tracing` (`db.Use(tracing.NewPlugin())`, emits `db.statement`). Anchor `#go-otelhttp-068--otelpgx-011-otel-sdk-143`.
- **Node.js**: `@opentelemetry/auto-instrumentations-node` (`--require …/register`, ESM needs `--import`; check the page), NestJS covered by the bundle, `PgInstrumentation({ enhancedDatabaseReporting: true })`, Prisma via `@prisma/instrumentation` (`prisma:engine:db_query` spans). The test runner must load the tracing file before the app. Anchor `#nodejs-nestjs--prisma-otel-sdk-057`.
- **Rust**: `tracing` + `tracing-opentelemetry` + `opentelemetry-otlp`; traces are Beta upstream. Diesel (`Instrumentation` hook) and SeaORM need spans with `db.statement`/`db.system` added by hand; sqlx emits events, not spans (community wrappers exist). Anchor `#rust-tracing-opentelemetry-031-diesel-seaorm`.
- **Ruby**: `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-all` with `c.use_all()`; `db_statement: :include` or `:obfuscate`. Say that which gem emits the SQL span (driver vs ActiveRecord) is unverified: check traces. Anchor `#ruby-rails--activerecord-opentelemetry-ruby`.
- **PHP**: extension (`pecl install opentelemetry`), `OTEL_PHP_AUTOLOAD_ENABLED=true`, `OTEL_TRACES_EXPORTER=otlp`, auto-pdo plus auto-laravel or auto-symfony + auto-doctrine. Say that hooks under PHPUnit CLI are unverified: check traces. Anchor `#php-laravel--eloquent-symfony--doctrine-opentelemetry-php`.

- [ ] **Step 1: Write the five files**
- [ ] **Step 2: Checker and link check** as in Task 5 Step 2
- [ ] **Step 3: Commit** `docs(skill): add the Go, Node.js, Rust, Ruby and PHP stack references`

---

### Task 8: CI references

**Files:**
- Create: `skills/perf-tests/references/ci/github-actions.md`, `gitlab-ci.md`, `jenkins.md`, `azure-devops.md`, `circleci.md`, `other.md`

Shared rule in every file: prefix the existing test step with `capture`, never add a parallel step that reruns the suite; run `analyze` on every branch and archive SARIF, JSON and HTML; the gate (`analyze --ci`) is shown, recommended on PRs only, never enabled by the skill; installation downloads the release and checks its SHA256.

- **GitHub Actions**: mirror Perf Sentinel's template behavior (SARIF to Code Scanning, sticky PR comment, PR gate from `.quality_gate.passed`, `::warning::` on trunk); needs `security-events: write` and `pull-requests: write`; say so. Link `/docs/CI#ci-integration-recipes`.
- **GitLab CI**: report-only runs with `|| exit 75`, JSON → `gl-code-quality-report.json`, final `analyze --ci`, `allow_failure: exit_codes: [75]`, `allow_failure: true` on the default branch.
- **Jenkins**: Warnings NG reads the SARIF; gate stage only when `env.CHANGE_ID != null`. A shared library or company template: describe the result to obtain (see `other.md`).
- **Azure DevOps**, **CircleCI**: Perf Sentinel ships no template: say so in `Showing results in the PR` (archive artifacts only, no new integration); gate via the exit code of `analyze --ci` on PR builds.
- **other.md**: the internal-layer case: list the four results to obtain (capture around tests, analyze + archive, ack file honored, optional PR gate) and ask the developer who owns the layer.

The templates live in the perf-sentinel repo's `docs/ci-templates/`, which the site does not publish: describe their behavior, link `/docs/CI`, do not link the repo files.

- [ ] **Step 1: Write the six files**
- [ ] **Step 2: Checker and link check** as in Task 5 Step 2
- [ ] **Step 3: Commit** `docs(skill): add the CI references`

---

### Task 9: Trial on `dotnet-svc` (feature flow)

**Files:**
- Modify: `skills/perf-tests/references/stacks/dotnet.md` (status line, and any fix the trial shows)
- Modify: `skills/perf-tests/SKILL.md` or other references only where the trial shows a gap

Setup: clone `https://github.com/Institut-du-Numerique-Responsable/perf-sentinel-simulation-lab` next to this repo, install `perf-sentinel` from the latest release with its checksum. On a throwaway branch of the lab, add a feature to `dotnet-svc` whose endpoint loops a query per item (deliberate N+1, ≥ 15 items). Run Claude with `claude --plugin-dir <this repo>` in the lab and invoke `/perf-sentinel:perf-tests`.

- [ ] **Step 1: Run the skill end to end**, answering its questions as a real developer would.
- [ ] **Step 2: Check the four outcomes**
  - the tests follow `dotnet-svc.tests` style and assert the business result;
  - the local capture file contains the diff's query (`perf-sentinel inspect --input <file>` shows it);
  - `analyze` reports `n_plus_one_sql` or `redundant_sql` on that template (Review Focus 4);
  - after the deliberate N+1 is fixed, rerunning the same tests reports nothing on that template.
- [ ] **Step 3: Port-taken check** (Review Focus 2): with `nc -l 4318` running, rerun the local step; expect the skill to report the `capture` exit 1 and rerun on other ports.
- [ ] **Step 4: Fix what failed** in the skill or reference, rerun the failing outcome, then set `dotnet.md` to `Status: tried end-to-end`.
- [ ] **Step 5: Gates and commit**

Run: `python3 scripts/check_plugin.py . && claude plugin validate --strict .`
```bash
git commit -am "docs(skill): mark the .NET reference as tried end-to-end"
```

---

### Task 10: Trial on `fastapi-svc` (bugfix flow)

**Files:**
- Modify: `skills/perf-tests/references/stacks/python.md`, plus gaps found

On a lab branch, commit a `fastapi-svc` endpoint with an N+1 on the base, then a second commit that fixes it. Invoke `/perf-sentinel:perf-tests bugfix <endpoint>` on the fix commit.

- [ ] **Step 1: Run the skill end to end**
- [ ] **Step 2: Check the outcomes**
  - the before/after run uses a separate worktree on the base;
  - the finding appears on the base and disappears on the fix;
  - the trace file contains the diff's query;
  - if the app runs in a container for the tests, the skill used `--listen-address 0.0.0.0` and `host.docker.internal` (Review Focus 3); otherwise run once with the app containerized to check it.
- [ ] **Step 3: Fix gaps, set** `python.md` to `Status: tried end-to-end`
- [ ] **Step 4: Gates and commit** `docs(skill): mark the Python reference as tried end-to-end`

---

### Task 11: Trial on an enterprise Spring Boot 4 service (Robin, work machine)

Run by Robin, since the service is not reachable from here. Nothing about the service is committed: only fixes to generic files.

- [ ] **Step 1: Feature flow and bugfix flow** on a branch of the service, same four outcomes as Task 9 and the before/after check of Task 10, with the existing Jenkins pipeline as the CI.
- [ ] **Step 2: Check the Spring trap**: the skill inspected whether `spring-boot-micrometer-tracing-test` is on the test classpath and whether the IT already export (do not add `@AutoConfigureTracing` if export already works).
- [ ] **Step 3: Fix gaps, set** `java-spring-boot.md` and `ci/jenkins.md` to `Status: tried end-to-end`, commit `docs(skill): mark the Spring Boot and Jenkins references as tried end-to-end`.

---

### Task 12: Release 0.1.0

**Files:**
- Modify: `CHANGELOG.md`, `README.md` (list which references are tried)

- [ ] **Step 1: Full gates**

Run: `python3 -m unittest scripts/test_check_plugin.py && python3 scripts/check_plugin.py . && claude plugin validate --strict . && claude plugin eval . --scaffold --trust-plugin --threshold 0.67`
Expected: all exit 0.

- [ ] **Step 2: Install from the marketplace in a clean session**: `/plugin marketplace add robintra/perf-sentinel-claude-plugin`, `/plugin install perf-sentinel@perf-sentinel`, check `/perf-sentinel:perf-tests` is listed.
- [ ] **Step 3: Grep for anything company-specific**: review `git grep -n -i` for internal names, hosts and paths before tagging.
- [ ] **Step 4: CHANGELOG `[0.1.0]`, commit, tag `v0.1.0`, push** (after Robin's go-ahead).

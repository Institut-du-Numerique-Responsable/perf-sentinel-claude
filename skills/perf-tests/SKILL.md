---
name: perf-tests
description: Writes performance integration tests for the current code change and runs them under Perf Sentinel, so N+1 queries, redundant calls and other I/O waste show up in the pull request instead of in production. Use when the user runs /perf-sentinel:perf-tests, or says yes after you proposed it. When the user says a feature or bugfix is done, or asks for a review, and the change adds or modifies database queries, outbound HTTP or RPC calls, or message publishing, do not start this skill. Finish what the user asked, then add one short line, phrased as a question, that proposes /perf-sentinel:perf-tests with the reason from the diff (for example a query issued once per item), and wait for a yes. Do not propose it when the change only touches UI, CSS, templates, docs or code with no I/O. Not for load tests or concurrent-user benchmarks (k6, Gatling, JMeter, Locust), because Perf Sentinel judges one trace at a time.
license: AGPL-3.0-only
compatibility: Needs a repository checkout, Docker for database-backed tests, and the perf-sentinel binary or permission to install it.
metadata:
  author: Robin Trassard
  repository: https://github.com/robintra/perf-sentinel-claude-plugin
allowed-tools: Bash(git diff *) Bash(git log *) Bash(git merge-base *) Bash(perf-sentinel --version) Bash(perf-sentinel analyze *) Bash(perf-sentinel inspect *)
---

# Performance integration tests under Perf Sentinel

## Consent comes first

If the user did not type `/perf-sentinel:perf-tests` and did not say yes to your proposal, do not run this flow. Propose it in one line and stop.

Once started, `Recon`, `Change scope` and `Business context` only read. Every step that writes a file, edits the build, installs a tool, starts a container, runs tests or touches the CI asks first and waits for a clear yes. One yes covers the action it answered, not the next one.

Your first message after the recon always ends with questions or scenarios to validate. Never write a test in that message, neither in a file nor as finished code in the reply.

Answer in the developer's language. The files you write follow the project's language.

## Arguments

`$ARGUMENTS` is free text that narrows the work: a ticket reference (`PROJ-1234`, `bugfix PROJ-1234`), a feature name, or nothing.

- If it looks like a ticket and a ticket tool (MCP server or a file in the repo) is available, read the ticket.
- If no tool can read it, say the ticket content could not be read, and keep the reference for the summary.
- `bugfix` in the argument, or a ticket that describes an incident, means the bugfix questions and the `Bugfix before/after` step apply.

## Recon

Read only. Report what you found in a few lines.

- [ ] Stack and framework version, from `pom.xml`, `build.gradle(.kts)`, `*.csproj`, `pyproject.toml`, `requirements*.txt`, `go.mod`, `package.json`, `Cargo.toml`, `Gemfile`, `composer.json`. Load the matching stack reference.
- [ ] CI, from `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `.circleci/` and others. Note whether a Perf Sentinel step (`perf-sentinel capture`, `perf-sentinel analyze`) already runs. If the CI goes through an internal layer you cannot read (shared library, company template), say so.
- [ ] OpenTelemetry instrumentation in place, and whether it can produce SQL and outbound HTTP spans. Say plainly whether it is present, partial or missing.
- [ ] Perf Sentinel config: `.perf-sentinel.toml`, `.perf-sentinel-acknowledgments.toml`.
- [ ] Existing integration test style: framework, naming, base classes, fixtures, real database or embedded one (Testcontainers, docker compose), how they are launched.

**No integration tests at all.** Say that the repository has no integration tests, so there is no style to copy. Do not present unit tests with mocks as an integration style. Propose the framework's idiomatic minimal harness by name (for example `@SpringBootTest` with a Testcontainers container of the production database engine, `WebApplicationFactory` for ASP.NET Core, `pytest` with `TestClient` for FastAPI), with a real database container if Docker is available. Ask before creating it.

**Several services or stacks.** When the repository holds several services and the change touches more than one, run the recon per service. Each service gets its own stack reference, its own scenario list and its own capture run. Never assume one stack for the whole repository. Write the reply as one section per service, in this shape:

```
### <service path> (<stack>)
- Entry points touched: ...
- Scenarios: ...
- Capture: its own `perf-sentinel capture` run around this service's test command
- Questions: ...
```

## Change scope

- [ ] Read the diff against the base branch (`git merge-base`, then `git diff`). If git is unavailable, say so and work from the files, the argument and the branch name, and ask the developer to confirm which files changed.
- [ ] When you cannot tell whether a service or path is part of the change, treat it as changed: give it the same full section as the others, say once that you kept it in scope, and let the developer remove it when validating. Do not mark its scenarios as optional or conditional.
- [ ] For each modified method, walk the callers up to the entry points: HTTP endpoint, message listener, scheduled job, batch, CLI command. Use the LSP if available, text search otherwise.
- [ ] Keep only the paths that do I/O Perf Sentinel sees: SQL, outbound HTTP, RPC, message publishing.
- [ ] List what you leave out (code with no I/O, UI, docs) and why, in one line each.

## Business context

Find answers yourself first: the ticket, the diff, the data model, the fixtures. If a Perf Sentinel Hub MCP tool is available, read the production findings for the touched endpoints. Without it, the step works the same.

Then ask only what you could not find.

**For a feature**, the typical usage at production scale:

- Who uses it, and how often?
- What data volume for a typical client, and for the biggest one?
- Are there peaks: end of month, bulk import, nightly batch?
- Does it grow over time, for example a history that keeps getting longer?
- Which filters and page sizes are really used?

**For a bugfix**, what happened:

- the finding or the incident
- the endpoint involved
- the data conditions that triggered it.

## Scenarios

- [ ] Show a short list before writing a single line of test. Format: endpoint, then the data shape. Example: `GET /clients/{id}/contracts`, a client with 200 contracts of 15 lines each.
- [ ] With several services, one list per service inside that service's section, headed by the service name and its stack, with its own planned capture run.
- [ ] Perf Sentinel minimums are a floor, not a target: 5 occurrences of the same query for an N+1, 10 for a critical one. The volume comes from the developer's answers. Thresholds per detector are in `references/perf-sentinel.md`.
- [ ] If the main risk is concurrent load rather than the work done by one request, say so and point to a load testing tool. This skill does not do load tests.
- [ ] Stop and wait for the developer to validate or correct the list.

## Instrumentation

Only when instrumentation is missing or incomplete. Ask before any change.

- [ ] Library or starter first, agent second. Prefer the dependency the framework offers (starter, extension, SDK configured in code, instrumentation packages declared in the project) over a zero-code agent. Use the agent when nothing else exists.
- [ ] If the project already uses an agent and a starter exists, keep the agent for this PR. Mention the starter as a separate migration.
- [ ] The spans must carry the SQL text (`db.query.text` or `db.statement`), the full URL of outbound calls, `service.name` on the resource, and `http.route` on server spans when possible.
- [ ] Sample at 100% during tests.
- [ ] Do not copy version numbers from the references. Check the current version on the official page at write time.
- [ ] Docs, in order: opentelemetry.io and the framework's own docs, then `https://perf-sentinel.dev/docs/INSTRUMENTATION` when it adds something.
- [ ] Check every test-time trap listed in the stack reference against the current docs (export switched off in tests, exporter set to `none`, a forked test JVM that cannot write to stdout, several workers or a reloader, libraries that emit events instead of spans).

## Writing the tests

Only after the scenarios are validated, and after a yes to create the files.

- [ ] Same framework, naming, base classes and database setup as the existing integration tests.
- [ ] A real database of the production engine when the project allows it. An N+1 or a query plan does not look the same on an embedded database.
- [ ] Data that matches the validated scenarios.
- [ ] Call the entry point the way a real client does (HTTP request, published message, job trigger), not internal classes.
- [ ] Assert the business result too. The test must stay true after a fix.
- [ ] The tests run in CI. Never skip or disable them on a CI environment variable.
- [ ] Keep the smallest data set that reproduces the production shape: 200 contracts if the biggest client has 200, not 10,000 clients. Reuse the existing containers and fixtures. If a test takes more than one minute locally, say so and propose a smaller data set.

## Local run

Ask before running anything.

- [ ] Check the prerequisites: the `perf-sentinel` binary (`perf-sentinel --version`), Docker if the tests need it, the test command.
- [ ] If the binary is missing, propose installing it from the official release with checksum verification.
- [ ] Run only the new tests: `perf-sentinel capture --output <file> -- <filtered test command>`. Write the capture file outside the build directory, since a `clean` step deletes it.
- [ ] Then `perf-sentinel analyze --input <file>`, with `--config .perf-sentinel.toml` when the project has one.
- [ ] Check the traces before reading the findings:
  - the file is not empty
  - it holds SQL or HTTP spans (`perf-sentinel inspect --input <file>` shows what was extracted)
  - it holds the queries or calls that match the code in the diff.

  If the diff's queries are absent, the test is wrong even with zero findings. Say so and fix the test.
- [ ] If a local run is impossible, say why in one sentence and move on. The CI will do the check.

## Bugfix before/after

Only for a bugfix. Ask before creating the worktree.

- [ ] Run the same test on the base branch code, in a separate git worktree.
- [ ] The finding must appear before and disappear after. If not, either the test does not reproduce the problem or the fix does not solve it. Say which one you suspect.
- [ ] The test goes through the public entry point so it can run on both sides.
- [ ] If the test does not compile or run on the base branch (changed API signature, migration), do this step on a best-effort basis, say so, and continue.

## Fixes

Only when there are findings. Load `references/fix-safety.md` before proposing any fix.

- [ ] Start from the finding and the Perf Sentinel suggestion, but do not trust the suggestion blindly.
- [ ] If a Perf Sentinel Hub MCP tool is available, read the finding history for the endpoint. Without it, the step works the same.
- [ ] One targeted fix at a time, checked against the Before, After and Decision lists of `references/fix-safety.md`.
- [ ] The developer decides whether to keep each fix.
- [ ] When the developer keeps a finding unfixed, propose the acknowledgment entry ready to paste, from the template in `references/perf-sentinel.md`: signature, reason, reviewer to fill in, and always an `expires_at` date. An entry without a date is permanent.
- [ ] Report the `unmatched_acknowledgment` entries the local run shows. They can be deleted.

## CI wiring

Only what Perf Sentinel already has. Load the CI reference that matches the detected CI. Ask before any change.

- [ ] Wrap the existing test step with `perf-sentinel capture`. Never add a second step that runs the suite again.
- [ ] Then `perf-sentinel analyze`, producing SARIF, JSON and HTML, archived with the build, on every branch.
- [ ] `.perf-sentinel-acknowledgments.toml`, versioned in the repo, is the register of unresolved findings: each entry has a reason, a reviewer and an expiration.
- [ ] Show results in the PR only through what the CI reference describes (SARIF to code scanning, PR comment, GitLab report). If that needs a token or a permission, say so.
- [ ] The gate is the team's choice. Recommend `analyze --ci` on pull requests, not on the main branch, show the change it makes, and do not turn it on yourself. The gate judges every trace of the suite with no comparison to the base branch, so findings from existing tests are the team's to fix or acknowledge.
- [ ] Recall the thresholds actually applied, from `.perf-sentinel.toml` or the defaults in `references/perf-sentinel.md`, and say which of the new tests would cross them if the code had a defect. Suggest `min_usable_span_ratio` so broken instrumentation fails the CI instead of passing green.
- [ ] The CI never feeds the Perf Sentinel Hub. It may read from it, nothing more.
- [ ] Docs: `https://perf-sentinel.dev/docs/CI` and `https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS`.

## Summary

End with a short summary:

- the scenarios tested
- the files created or modified
- the local result: findings, or why there was no local run
- the fixes proposed and their status
- what the CI will do
- what the skill did not cover, and why.

## Untried references

Each stack and CI reference starts with a status line. When it reads `Status: written from official docs, not yet tried`:

- fetch the official page linked in the reference before acting on it
- do the trace check of `Local run` even when the run looks green.

## Reference map

- `references/perf-sentinel.md`: load at `Scenarios` and `CI wiring`. Detectors and what makes each fire, gate defaults, CLI, exit codes, acknowledgment template, perf-sentinel.dev links.
- `references/fix-safety.md`: load at `Fixes`, before proposing any fix.
- `references/stacks/java-spring-boot.md`, `java-quarkus.md`, `java-micronaut.md`, `dotnet.md`, `python.md`, `go.md`, `node.md`, `rust.md`, `ruby.md`, `php.md`: load the one matching each service's stack at `Recon`, use it at `Instrumentation`, `Writing the tests` and `Local run`.
- `references/ci/github-actions.md`, `gitlab-ci.md`, `jenkins.md`, `azure-devops.md`, `circleci.md`: load the one matching the detected CI at `CI wiring`. `references/ci/other.md` for any other CI or an unreadable internal layer.

# CircleCI

Status: written from official docs, not yet tried

## Detecting it

- [ ] `.circleci/config.yml`, plus any file it pulls in. Find the job that runs the integration tests and the workflow that calls it.
- [ ] A Perf Sentinel step already there: `grep -n "perf-sentinel" .circleci/config.yml`. If it exists, extend it.
- [ ] An `orbs:` entry or a `commands:` or `jobs:` section coming from a company orb around the test step: if you cannot read it, load `other.md` as well.
- [ ] The VCS integration (GitHub App, GitHub OAuth, Bitbucket Cloud, GitLab). It decides which pull request variables exist, see the gate below.

## Wrapping the test step

- [ ] Install Perf Sentinel before the test step, from the official release with the SHA256 check, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). Use the current release tag in an environment variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file.
- [ ] Prefix the existing test command with `capture`. Never add a second job or step that reruns the suite.
- [ ] Set the exporter variables on the step with `environment:`: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Keep the executor the job already uses. The install lines assume a Linux executor with `curl` and `sha256sum`. When the tests run in a secondary container, the exporter endpoint and `--listen-address` need care: [perf-sentinel.md](../perf-sentinel.md), section `capture`.

```yaml
- run:
    name: Integration tests under capture
    command: |
      perf-sentinel capture --output /tmp/traces.ndjson -- <existing test command>
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: http://localhost:4318
      OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
      OTEL_TRACES_SAMPLER: always_on
```

`<existing test command>` is a placeholder: keep the command the step already runs.

## Analyze and archive

- [ ] A report-only step after the tests, with no `--ci`, on every branch, with `when: always` so the report exists when the tests failed.
- [ ] SARIF and JSON from `analyze --format`, HTML from `report`. Write them into one folder.
- [ ] Archive the folder with `store_artifacts`. It runs even when an earlier step failed, but not when the job is cancelled or times out.
- [ ] The ack file `.perf-sentinel-acknowledgments.toml` is read from the working directory. Run from the repository root, or pass `--acknowledgments`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.

```yaml
- run:
    name: Perf Sentinel analyze
    when: always
    command: |
      set -euo pipefail
      mkdir -p perf-sentinel-out
      perf-sentinel analyze --input /tmp/traces.ndjson --config .perf-sentinel.toml --format sarif > perf-sentinel-out/findings.sarif
      perf-sentinel analyze --input /tmp/traces.ndjson --config .perf-sentinel.toml --format json > perf-sentinel-out/report.json
      perf-sentinel report --input /tmp/traces.ndjson --config .perf-sentinel.toml --output perf-sentinel-out/report.html
- store_artifacts:
    path: perf-sentinel-out
    destination: perf-sentinel
```

## Showing results in the PR

- [ ] Perf Sentinel ships no CircleCI template. Nothing in its docs describes a PR check, comment or annotation for this CI.
- [ ] So the results are archived only: the job's Artifacts tab holds the SARIF, the JSON and the HTML dashboard. Tell the developer where to find them.
- [ ] Do not add an orb, a PR comment script or a GitHub token. That would be a new integration. If the developer asks for one, say it is outside what Perf Sentinel documents for CircleCI.

## Optional gate

The gate is the team's choice. Recommend it on pull request builds only, show the change, never turn it on yourself.

- [ ] A step running `perf-sentinel analyze --ci --input ... --config ...` after the report-only step. Its exit code is the verdict: `1` for a breach, `75` for a tooling error, [perf-sentinel.md](../perf-sentinel.md), section `Exit codes`.
- [ ] Detect a pull request build with `CIRCLE_PULL_REQUEST`, which holds the PR URL. It exists for GitHub and Bitbucket Cloud only, and one URL is picked at random when several PRs match. With another VCS, or when the variable is unreliable, ask the developer how the team tells a PR build from a branch build, for example by branch name.
- [ ] On other builds the step does nothing and the job stays green.
- [ ] A checksum mismatch must always fail the job.
- [ ] To block merging, the team makes the CircleCI check required in the branch protection of its VCS. That setting is theirs.

```yaml
- run:
    name: Perf Sentinel quality gate (pull requests only)
    command: |
      if [ -n "${CIRCLE_PULL_REQUEST:-}" ]; then
        perf-sentinel analyze --ci --input /tmp/traces.ndjson --config .perf-sentinel.toml
      fi
```

## Links

- Perf Sentinel, CI mode and exit codes: https://perf-sentinel.dev/docs/CI#ci-mode-batch-analysis
- Perf Sentinel, gate philosophy: https://perf-sentinel.dev/docs/CI#quality-gate-philosophy
- Perf Sentinel, acknowledgments: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS
- CircleCI, configuration reference: https://circleci.com/docs/reference/configuration-reference/
- CircleCI, built-in variables (`CIRCLE_PULL_REQUEST`): https://circleci.com/docs/reference/variables/

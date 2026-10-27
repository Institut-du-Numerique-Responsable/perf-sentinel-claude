# GitLab CI

Status: written from official docs, not yet tried

## Detecting it

- [ ] `.gitlab-ci.yml` at the root, plus any file pulled in with `include:`. Find the job that runs the integration tests and its stage.
- [ ] A Perf Sentinel job already there: `grep -n "perf-sentinel" .gitlab-ci.yml`. If it exists, extend it.
- [ ] An `include:` of a company template or a `project:` include you cannot read, or a job that `extends:` one: load `other.md` as well.

## Wrapping the test step

- [ ] The test job needs the `perf-sentinel` binary, since `capture` runs in it. Install it from the official release with the SHA256 check, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). Use the current release tag in a variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file.
- [ ] The release asset lands in the current directory as `perf-sentinel-linux-amd64`, not on `PATH`. Install it as `${CI_PROJECT_DIR}/bin/perf-sentinel` and call it by that absolute path in `capture`, `analyze` and `report`. Perf Sentinel's template does the same, because some executors do not carry a `before_script` `PATH` export into `script`.
- [ ] Each job has its own workspace. Perf Sentinel's template installs the binary in the analyze job only, but `capture` runs in the test job, so the install must run in the test job too. Reuse the same lines in both with `!reference` or `extends`, or run `analyze` in the test job itself.
- [ ] Prefix the existing `script:` command with `capture`. Never add a second job that reruns the suite.
- [ ] Set the exporter variables on the job: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Hand the capture file to the next job with `artifacts:` and `dependencies:` or `needs:`.

```yaml
integration-tests:
  variables:
    OTEL_EXPORTER_OTLP_ENDPOINT: "http://localhost:4318"
    OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
    OTEL_TRACES_SAMPLER: "always_on"
  script:
    # install lines first, as above
    - "${CI_PROJECT_DIR}/bin/perf-sentinel" capture --output traces.ndjson -- <existing test command>
  artifacts:
    paths: [traces.ndjson]
    expire_in: 1 day
```

`<existing test command>` is a placeholder: keep the command the job already runs.

## Analyze and archive

- [ ] A `perf-sentinel` job in a later stage, report-only first. End each report-only command with `|| exit 75`, so a tooling failure has its own exit code and is never read as a gate breach.
- [ ] `exit 75` blocks a merge request unless the job carries `allow_failure: exit_codes: [75]`. Put it in the job from the start, as in the snippet, so an empty capture never reddens a pipeline when no gate is enabled. Only the optional gate may fail the build.
- [ ] SARIF and JSON from `analyze --format`, HTML from `report`. Archive all three with `artifacts:` and `when: always`, on every branch.
- [ ] Convert the JSON to `gl-code-quality-report.json` with `jq`: one entry per finding, with `description`, `fingerprint`, `severity` and `location`. Perf Sentinel's template maps `critical` to `critical`, `warning` to `major` and the rest to `info`, and uses the finding's `code_location` for the path and line. Read the exact filter in the CI recipes link below instead of inventing one.
- [ ] A failing `jq` is a bug in the filter, so it must not exit `75`.
- [ ] The ack file `.perf-sentinel-acknowledgments.toml` is read from the working directory. Run from `$CI_PROJECT_DIR`, or pass `--acknowledgments`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.

```yaml
perf-sentinel:
  stage: perf-sentinel
  dependencies: [integration-tests]
  script:
    # install lines first, as above
    - "${CI_PROJECT_DIR}/bin/perf-sentinel" analyze --input traces.ndjson --config .perf-sentinel.toml --format sarif > findings.sarif || exit 75
    - "${CI_PROJECT_DIR}/bin/perf-sentinel" analyze --input traces.ndjson --config .perf-sentinel.toml --format json > perf-sentinel-report.json || exit 75
    - "${CI_PROJECT_DIR}/bin/perf-sentinel" report --input traces.ndjson --config .perf-sentinel.toml --output report.html || exit 75
    # jq conversion to gl-code-quality-report.json goes here
  allow_failure:
    exit_codes: [75]
  artifacts:
    when: always
    paths: [findings.sarif, perf-sentinel-report.json, report.html]
    reports:
      codequality: gl-code-quality-report.json
    expire_in: 1 week
```

## Showing results in the PR

- [ ] Findings show in the merge request's Code Quality widget, from `artifacts:reports:codequality`. No token and no extra permission, the job artifacts are enough.
- [ ] Check the GitLab tier and version against the Code Quality page below before promising a widget layout.
- [ ] The SARIF file is archived only. GitLab does not read SARIF from this job.
- [ ] No other integration. The HTML report through GitLab Pages is an opt-in recipe in the Perf Sentinel docs: mention it, do not set it up.

## Optional gate

The gate is the team's choice. Recommend it on merge requests only, show the change, never turn it on yourself.

- [ ] Perf Sentinel's template ends the job `script:` with `"${CI_PROJECT_DIR}/bin/perf-sentinel" analyze --ci --input ... --config ... --format json > /dev/null`. It runs only after every report-only command succeeded, and keeps its own exit code: `1` for a breach.
- [ ] `allow_failure: exit_codes: [75]`, already in the job above, lets a tooling failure through without blocking the merge request. It stays on the job: `rules:allow_failure` accepts only a boolean, and the CI lint rejects the mapping form there.
- [ ] `rules:` runs the job on `merge_request_event` and on the default branch. The default-branch rule carries `allow_failure: true`, so a breach on trunk never turns the pipeline red.
- [ ] A checksum mismatch must always block. Do not add `|| exit 75` to the checksum line.
- [ ] To block merging on a red job, the team enables "Pipelines must succeed" in the project's merge settings. Say so and leave it to them.

```yaml
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      allow_failure: true
```

## Links

- Perf Sentinel, CI recipes and the GitLab CI template: https://perf-sentinel.dev/docs/CI#ci-integration-recipes
- Perf Sentinel, gate philosophy: https://perf-sentinel.dev/docs/CI#quality-gate-philosophy
- Perf Sentinel, tooling failures versus breaches (the `75` convention): https://perf-sentinel.dev/docs/CI#tooling-failures-vs-quality-gate-breaches
- Perf Sentinel, exit codes: https://perf-sentinel.dev/docs/CI#exit-codes
- Perf Sentinel, acknowledgments: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS
- GitLab, CI/CD YAML reference: https://docs.gitlab.com/ci/yaml/
- GitLab, `!reference` and `extends`: https://docs.gitlab.com/ci/yaml/yaml_optimization/
- GitLab, Code Quality: https://docs.gitlab.com/ci/testing/code_quality/

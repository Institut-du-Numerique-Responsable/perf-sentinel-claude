# GitLab CI

Status: tried end-to-end

Tried: `gitlab-ci-local` with the Docker executor on a native arm64 Docker host, the install job, a Maven wrapper with Failsafe and Testcontainers through the host Docker socket, a branch pipeline, failing tests, the gate on a simulated merge request pipeline with and without an N+1, a missing config file, a failed download, a corrupted asset, and the `jq` output checked against the Code Quality field list. Not tried: a GitLab instance (the merge request reports, the baseline comparison, the CI lint and "Pipelines must succeed" were not seen), real merge request variables (set by hand, and `gitlab-ci-local` puts a job with no `rules:` in merge request pipelines, which GitLab does not), the skipped stages after a failed `.pre` job (`gitlab-ci-local` ran the test stage anyway), `needs:`, a shell executor or a runner that reuses its build directory, the `amd64` asset on a native amd64 runner (the install script ran once under emulation), findings with `code.*` attributes (every path was `unknown`), the GitLab Pages recipe.

## Detecting it

- [ ] `.gitlab-ci.yml` at the root, plus any file pulled in with `include:`. Find the job that runs the integration tests and its stage.
- [ ] A Perf Sentinel job already there: `grep -n "perf-sentinel" .gitlab-ci.yml`. If it exists, extend it.
- [ ] An `include:` of a company template or a `project:` include you cannot read, or a job that `extends:` one: load `other.md` as well.

## Wrapping the test step

- [ ] Install the binary in its own job in the `.pre` stage, from the official release with the SHA256 check, as in the snippet. Use the current release tag in a variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file. The release URL takes the tag with its `v`: `releases/download/v${PERF_SENTINEL_VERSION}`.
- [ ] Do not download in the test job. Test images often lack `curl` (`eclipse-temurin` ships neither `curl` nor `wget`), and an install line that fails there stops the job before the tests run. The install job uses its own small image and hands `bin/perf-sentinel` to the test and analyze jobs with `artifacts:` and `dependencies:` (or `needs:`, if the test job already uses it). The asset is statically linked, so it runs in any Linux image of the same architecture.
- [ ] The asset must match the runner architecture: `perf-sentinel-linux-amd64` when `uname -m` prints `x86_64`, `perf-sentinel-linux-arm64` when it prints `aarch64`. The snippet picks it from `uname -m`. When the project has runners of both architectures, give the install job the test job's `tags:`.
- [ ] A failed download exits `75`, which `allow_failure: exit_codes: [75]` lets through. The checksum check has no `|| exit 75`: a mismatch fails the pipeline.
- [ ] Call the binary as `${CI_PROJECT_DIR}/bin/perf-sentinel` in `capture`, `analyze` and `report`. Perf Sentinel's template does the same, because some executors do not carry a `before_script` `PATH` export into `script`. A script line that starts with a double quote is read by YAML as a quoted string and the file is rejected, so leave the path unquoted on a single line or use a `- |` block.
- [ ] Prefix the existing `script:` command with `capture`. Never add a second job that reruns the suite.
- [ ] Run the bare test command when the binary is missing, as in the snippet. After a failed download, `capture` would not start and the tests would not run.
- [ ] A `cd` earlier in the script moves the working directory for the following lines. Write the capture path from `${CI_PROJECT_DIR}`, since `artifacts:paths` is always relative to the project root.
- [ ] Set the exporter variables on the job: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Put `when: always` on the test job's `artifacts:`, since the default `on_success` drops the capture when the tests fail.

```yaml
variables:
  PERF_SENTINEL_VERSION: "<current release, without the v>"
  PERF_SENTINEL_TRACES: "traces.ndjson"

perf-sentinel-install:
  stage: .pre
  image: debian:bookworm-slim
  script:
    - apt-get update && apt-get install -y --no-install-recommends curl ca-certificates || exit 75
    - |
      case "$(uname -m)" in
        x86_64) ASSET=perf-sentinel-linux-amd64 ;;
        aarch64|arm64) ASSET=perf-sentinel-linux-arm64 ;;
        *) echo "unsupported architecture: $(uname -m)" >&2; exit 75 ;;
      esac
      BASE_URL="https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/releases/download/v${PERF_SENTINEL_VERSION}"
      curl -sSLf -o "$ASSET" "$BASE_URL/$ASSET" || exit 75
      curl -sSLf -o SHA256SUMS.txt "$BASE_URL/SHA256SUMS.txt" || exit 75
      # no exit 75 here: a checksum mismatch always fails the pipeline
      grep "$ASSET" SHA256SUMS.txt | sha256sum -c -
      mkdir -p bin
      install -m 0755 "$ASSET" bin/perf-sentinel
      bin/perf-sentinel --version
  allow_failure:
    exit_codes: [75]
  artifacts:
    paths: [bin/perf-sentinel]
    expire_in: 1 day
  # same rules: as the test job

integration-tests:
  dependencies: [perf-sentinel-install]
  variables:
    OTEL_EXPORTER_OTLP_ENDPOINT: "http://localhost:4318"
    OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
    OTEL_TRACES_SAMPLER: "always_on"
  script:
    # no binary after a failed download: run the tests anyway
    - |
      if [ -x "${CI_PROJECT_DIR}/bin/perf-sentinel" ]; then
        "${CI_PROJECT_DIR}/bin/perf-sentinel" capture --output "${CI_PROJECT_DIR}/${PERF_SENTINEL_TRACES}" -- <existing test command>
      else
        <existing test command>
      fi
  artifacts:
    when: always
    paths: ["${PERF_SENTINEL_TRACES}"]
    expire_in: 1 day
```

`<existing test command>` is a placeholder: keep the command the job already runs, the same in both branches, after any `cd` it already has. The `if` block sets no shell option, so the team's command runs as before.

## Analyze and archive

- [ ] A `perf-sentinel` job in a later stage, report-only first. `when: always` on the job keeps the report when the tests fail, otherwise the later stage is skipped. End each report-only command with `|| exit 75`, so a tooling failure has its own exit code and is never read as a gate breach.
- [ ] `exit 75` blocks a merge request unless the job carries `allow_failure: exit_codes: [75]`. Put it in the job from the start, as in the snippet, so an empty capture never reddens a pipeline when no gate is enabled. Only the optional gate may fail the build.
- [ ] The commands pass `--config .perf-sentinel.toml`. With no such file `analyze` exits 75 and nothing is reported, so create the file first (ask) or drop `--config`, as in `CI wiring` of SKILL.md.
- [ ] SARIF and JSON from `analyze --format`, HTML from `report`. Archive all three with `artifacts:` and `when: always`, on every branch.
- [ ] Convert the JSON to `gl-code-quality-report.json` with the `jq` filter of the snippet: one entry per finding, with the fields GitLab requires (`description`, `check_name`, `fingerprint`, `severity`, `location.path`, `location.lines.begin`). It maps `critical` to `critical`, `warning` to `major` and the rest to `info`, and uses the finding's `code_location` for the path and line, `unknown` and `1` when the spans carry no `code.*` attributes.
- [ ] Two lines differ from Perf Sentinel's template, keep them. The template has no `check_name`, which the Code Quality format requires. It builds the fingerprint from the `trace_id`, which changes on every run, so a finding never matches the target branch's baseline. The finding's `signature` is stable across runs, and GitLab shows findings with the same fingerprint as one entry.
- [ ] The analyze job needs `jq`. Install it in the job's image, with `|| exit 75` on the install line, as in the snippet.
- [ ] A failing `jq` is a bug in the filter, so it must not exit `75`.
- [ ] The ack file `.perf-sentinel-acknowledgments.toml` is read from the working directory. Run from `$CI_PROJECT_DIR`, or pass `--acknowledgments`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.

```yaml
perf-sentinel:
  stage: perf-sentinel
  image: debian:bookworm-slim
  dependencies: [perf-sentinel-install, integration-tests]
  when: always
  before_script:
    - apt-get update && apt-get install -y --no-install-recommends jq || exit 75
  script:
    - ${CI_PROJECT_DIR}/bin/perf-sentinel analyze --input "${PERF_SENTINEL_TRACES}" --config .perf-sentinel.toml --format sarif > findings.sarif || exit 75
    - ${CI_PROJECT_DIR}/bin/perf-sentinel analyze --input "${PERF_SENTINEL_TRACES}" --config .perf-sentinel.toml --format json > perf-sentinel-report.json || exit 75
    - ${CI_PROJECT_DIR}/bin/perf-sentinel report --input "${PERF_SENTINEL_TRACES}" --config .perf-sentinel.toml --output report.html || exit 75
    - |
      jq '[
        .findings[] | {
          description: ("[" + .type + "] " + .suggestion),
          check_name: .type,
          fingerprint: .signature,
          severity: (
            if .severity == "critical" then "critical"
            elif .severity == "warning" then "major"
            else "info" end
          ),
          location: {
            path: (.code_location.filepath // "unknown"),
            lines: { begin: (.code_location.lineno // 1) }
          }
        }
      ]' perf-sentinel-report.json > gl-code-quality-report.json
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

- [ ] Findings show in the merge request's reports, from `artifacts:reports:codequality`. No token and no extra permission, the job artifacts are enough. GitLab marks a finding new or resolved against a baseline pipeline on the target branch, so the job must also run there, as the rules below do.
- [ ] Check the GitLab tier and version against the Code Quality page below before promising a widget layout.
- [ ] The SARIF file is archived only. GitLab does not read SARIF from this job.
- [ ] No other integration. The HTML report through GitLab Pages is an opt-in recipe in the Perf Sentinel docs: mention it, do not set it up.

## Optional gate

The gate is the team's choice. Recommend it on merge requests only, show the change, never turn it on yourself.

- [ ] Add the gate as the last line of the job `script:`, after the `jq` conversion: `- ${CI_PROJECT_DIR}/bin/perf-sentinel analyze --ci --input "${PERF_SENTINEL_TRACES}" --config .perf-sentinel.toml --format json > /dev/null`. It runs only after every report-only command succeeded, and keeps its own exit code: `1` for a breach. Perf Sentinel's template writes the binary path in double quotes inside a `- |` block. On a single line, a leading double quote breaks the YAML.
- [ ] The gate runs on every pipeline. Outside merge requests a breach shows as a job allowed to fail, and the pipeline passes with a warning.
- [ ] `allow_failure: exit_codes: [75]`, already in the job above, lets a tooling failure through without blocking the merge request. It stays on the job: `rules:allow_failure` accepts only a boolean, and the CI lint rejects the mapping form there.
- [ ] `rules:` runs the job on `merge_request_event`, on the default branch, and on every other pipeline through a final catch-all rule, so other branches keep the report. The default-branch and catch-all rules carry `allow_failure: true`, so a breach there never turns the pipeline red. Each rule sets `when: always` to keep the report-only behavior of the job, because `rules:` overrides the job-level `when:`.
- [ ] Merge request pipelines must run the install and test jobs too, otherwise `dependencies:` points at a job that is not in the pipeline and the config is rejected. A job with no `rules:` and no `only:` is left out of merge request pipelines by default. Check the test job's own `rules:`, and give the install job the same ones.
- [ ] Without `workflow:rules`, a branch with an open merge request runs a branch pipeline and a merge request pipeline, and GitLab warns about the catch-all rule. Choosing between the two is a `workflow:rules` change for the whole project: mention it, do not make it.
- [ ] A checksum mismatch must always block. Do not add `|| exit 75` to the checksum line of the install job.
- [ ] To block merging on a red job, the team enables "Pipelines must succeed" in the project's merge settings. Say so and leave it to them.

```yaml
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
      when: always
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      when: always
      allow_failure: true
    - when: always
      allow_failure: true
```

## Links

- Perf Sentinel, CI recipes and the GitLab CI template: https://perf-sentinel.dev/docs/CI#ci-integration-recipes
- Perf Sentinel, gate philosophy: https://perf-sentinel.dev/docs/CI#quality-gate-philosophy
- Perf Sentinel, tooling failures versus breaches (the `75` convention): https://perf-sentinel.dev/docs/CI#tooling-failures-vs-quality-gate-breaches
- Perf Sentinel, exit codes: https://perf-sentinel.dev/docs/CI#exit-codes
- Perf Sentinel, acknowledgments: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS
- GitLab, CI/CD YAML reference: https://docs.gitlab.com/ci/yaml/
- GitLab, job rules and merge request pipelines: https://docs.gitlab.com/ci/jobs/job_rules/
- GitLab, Code Quality: https://docs.gitlab.com/ci/testing/code_quality/

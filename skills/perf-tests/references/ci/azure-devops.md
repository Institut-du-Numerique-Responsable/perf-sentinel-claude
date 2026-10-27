# Azure DevOps

Status: written from official docs, not yet tried

## Detecting it

- [ ] `azure-pipelines.yml` (or another YAML path named in the pipeline definition), plus any `template:` references. Find the job and the step that runs the integration tests.
- [ ] A Perf Sentinel step already there: `grep -rn "perf-sentinel" azure-pipelines*.yml`. If it exists, extend it.
- [ ] A `template:` from another repository (`resources: repositories:`) or a company template around the test step: if you cannot read it, load `other.md` as well.
- [ ] Where the repository lives. YAML `pr:` triggers work only for GitHub and Bitbucket Cloud. With Azure Repos Git, a branch policy for build validation starts the PR build, and that policy is a repository setting, not YAML.

## Wrapping the test step

- [ ] Install Perf Sentinel before the test step, from the official release with the SHA256 check, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). Use the current release tag in a pipeline variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file.
- [ ] The release asset lands in the current directory as `perf-sentinel-linux-amd64`, not on `PATH`, and every step is a new shell. Install it as `perf-sentinel` in a folder under `$(Agent.TempDirectory)`, then print `##vso[task.prependpath]<absolute folder>`. The agent adds it to `PATH` for the later tasks, never for the step that prints it, so the install is its own step before the tests. The docs ask for absolute paths there.
- [ ] Prefix the existing test command with `capture`. Never add a second step that reruns the suite.
- [ ] Set the exporter variables on the step with `env:`: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Keep the agent pool the job already uses. The install lines assume a Linux agent with `curl` and `sha256sum`.

```yaml
- bash: |
    set -euo pipefail
    BASE_URL="https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/releases/download/v$(PERF_SENTINEL_VERSION)"
    curl -sSLf -o perf-sentinel-linux-amd64 "${BASE_URL}/perf-sentinel-linux-amd64"
    curl -sSLf -o SHA256SUMS.txt "${BASE_URL}/SHA256SUMS.txt"
    grep 'perf-sentinel-linux-amd64' SHA256SUMS.txt | sha256sum -c -
    mkdir -p "$(Agent.TempDirectory)/ps-bin"
    install -m 0755 perf-sentinel-linux-amd64 "$(Agent.TempDirectory)/ps-bin/perf-sentinel"
    echo "##vso[task.prependpath]$(Agent.TempDirectory)/ps-bin"
  displayName: Install Perf Sentinel
- bash: |
    set -euo pipefail
    perf-sentinel capture --output "$(Agent.TempDirectory)/traces.ndjson" \
      -- <existing test command>
  displayName: Integration tests under capture
  env:
    OTEL_EXPORTER_OTLP_ENDPOINT: http://localhost:4318
    OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
    OTEL_TRACES_SAMPLER: always_on
```

`<existing test command>` is a placeholder: keep the command the step already runs. A task that cannot be prefixed goes in a script, and the script is wrapped.

## Analyze and archive

- [ ] A report-only step after the tests, with no `--ci`, on every branch, with `condition: succeededOrFailed()` so the report exists when the tests failed.
- [ ] Give it `continueOnError: true`. An empty capture makes `analyze` exit `75`, and without the tolerance that would fail every branch with no gate enabled. The step then ends as "succeeded with issues", the build is partially succeeded instead of failed. Only the optional gate may fail the build.
- [ ] On success the step sets a variable (`##vso[task.setvariable variable=psReport]true`), which the gate checks. A variable set in a step is available to the later steps of the job only.
- [ ] SARIF and JSON from `analyze --format`, HTML from `report`. Write them into one folder.
- [ ] Publish the folder with a `publish:` step (shortcut of the `PublishPipelineArtifact@1` task) and `condition: succeededOrFailed()`. On Azure DevOps Server the `publish` step is not supported, use the Publish Build Artifacts task there.
- [ ] The ack file `.perf-sentinel-acknowledgments.toml` is read from the working directory. Run from the repository root, or pass `--acknowledgments`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.

```yaml
- bash: |
    set -euo pipefail
    T="$(Agent.TempDirectory)/traces.ndjson"
    mkdir -p perf-sentinel-out
    perf-sentinel analyze --input "$T" --config .perf-sentinel.toml --format sarif > perf-sentinel-out/findings.sarif
    perf-sentinel analyze --input "$T" --config .perf-sentinel.toml --format json > perf-sentinel-out/report.json
    perf-sentinel report --input "$T" --config .perf-sentinel.toml --output perf-sentinel-out/report.html
    echo "##vso[task.setvariable variable=psReport]true"
  displayName: Perf Sentinel analyze
  condition: succeededOrFailed()
  continueOnError: true
- publish: perf-sentinel-out
  artifact: perf-sentinel
  condition: succeededOrFailed()
```

## Showing results in the PR

- [ ] Perf Sentinel ships no Azure DevOps template. Nothing in its docs describes a PR widget, comment or annotation for this CI.
- [ ] So the results are archived only: the `perf-sentinel` artifact of the run holds the SARIF, the JSON and the HTML dashboard. Tell the developer where to find it (the run's summary page, Artifacts).
- [ ] Do not add a SARIF viewer extension, a PR comment script or a service connection. That would be a new integration, and any token it needs is the team's to decide. If the developer asks for one, say it is outside what Perf Sentinel documents for Azure DevOps.

## Optional gate

The gate is the team's choice. Recommend it on pull request builds only, show the change, never turn it on yourself.

- [ ] A step running `perf-sentinel analyze --ci --input ... --config ...` after the report-only step. Its exit code is the verdict: `1` for a breach, `75` for a tooling error, [perf-sentinel.md](../perf-sentinel.md), section `Exit codes`.
- [ ] Run it on pull request builds only, with `condition: and(succeeded(), eq(variables['psReport'], 'true'), eq(variables['Build.Reason'], 'PullRequest'))`. Other builds skip it and stay green. `Build.Reason` is `PullRequest` when a branch policy build or a PR trigger starts the build.
- [ ] A tooling failure of the download or of `analyze` is not a breach. The `psReport` variable in the condition runs the gate only after the report-only step produced a report.
- [ ] A checksum mismatch must always fail the build.
- [ ] To block completing the PR on a red build, the team sets the build validation branch policy as required. That is a repository setting, say so and leave it to them.

```yaml
- bash: perf-sentinel analyze --ci --input "$(Agent.TempDirectory)/traces.ndjson" --config .perf-sentinel.toml
  displayName: Perf Sentinel quality gate (pull requests only)
  condition: and(succeeded(), eq(variables['psReport'], 'true'), eq(variables['Build.Reason'], 'PullRequest'))
```

## Links

- Perf Sentinel, CI mode and exit codes: https://perf-sentinel.dev/docs/CI#ci-mode-batch-analysis
- Perf Sentinel, gate philosophy: https://perf-sentinel.dev/docs/CI#quality-gate-philosophy
- Perf Sentinel, acknowledgments: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS
- Azure Pipelines, YAML schema: https://learn.microsoft.com/en-us/azure/devops/pipelines/yaml-schema/
- Azure Pipelines, `pr` trigger: https://learn.microsoft.com/en-us/azure/devops/pipelines/yaml-schema/pr
- Azure Pipelines, `publish` step: https://learn.microsoft.com/en-us/azure/devops/pipelines/yaml-schema/steps-publish
- Azure Pipelines, logging commands (`task.prependpath`, `task.setvariable`): https://learn.microsoft.com/en-us/azure/devops/pipelines/scripts/logging-commands
- Azure Pipelines, conditions: https://learn.microsoft.com/en-us/azure/devops/pipelines/process/conditions
- Azure Pipelines, predefined variables (`Build.Reason`): https://learn.microsoft.com/en-us/azure/devops/pipelines/build/variables
- Azure Repos, branch policies and build validation: https://learn.microsoft.com/en-us/azure/devops/repos/git/branch-policies#build-validation

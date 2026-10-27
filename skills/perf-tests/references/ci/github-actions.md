# GitHub Actions

Status: tried end-to-end

Tried: one job on a Spring Boot Maven project with Testcontainers, run locally with `act` on a native arm64 Ubuntu 24.04 runner image: a push, failing tests on a pull request, the gate with and without an N+1 on a pull request, a missing config file, a failed download and a checksum mismatch, plus `actionlint`. Not tried: GitHub itself (`act` simulated the `push` and `pull_request` events, and the SARIF upload and the sticky comment ran with no valid token, so neither reached a real Code Scanning or pull request), `actions/upload-artifact` v7 (the `act` artifact server rejects it, v4 ran in its place), the `amd64` asset, a self-hosted runner and its reused workspace, a pull request from a fork, a cancelled run, branch protection.

## Detecting it

- [ ] Workflow files in `.github/workflows/*.yml`. Find the job and the step that runs the integration tests.
- [ ] A Perf Sentinel step already there: `grep -rn "perf-sentinel" .github/workflows`. If it exists, extend it, never add a second one.
- [ ] A reusable workflow or composite action (`uses: ./...` or `uses: <org>/<repo>/.github/workflows/...`) around the test step: if you cannot read it, load `other.md` as well.

## Wrapping the test step

- [ ] Install Perf Sentinel in steps of their own before the test step, from the official release with the SHA256 check, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). Use the current release tag in a workflow variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file.
- [ ] The asset must match the runner architecture: GitHub also offers arm64 Linux runners. The download step picks `perf-sentinel-linux-amd64` or `perf-sentinel-linux-arm64` from `uname -m`, so an unknown architecture is a tooling failure, never a red build.
- [ ] Split the install in two steps, as Perf Sentinel's template does. The download gets `continue-on-error: true`: a failed download is a tooling failure. The checksum check runs in the next step, only when the download succeeded, with no tolerance: a mismatch must fail the job.
- [ ] The asset lands in the current directory, not on `PATH`. Install it as `bin/perf-sentinel` under the workspace and append that directory to `$GITHUB_PATH`. A path added to `$GITHUB_PATH` applies to the later steps only, never to the step that adds it, so the install cannot share a step with the tests.
- [ ] Prefix the existing test command with `capture`. Never add a second step that reruns the suite.
- [ ] Run the bare test command when the install did not succeed, as in the snippet. Without the binary, `capture` would not start, the tests would not run and the job would turn red for a tooling problem.
- [ ] Add no `set` line to the test step and keep its `shell:` and `working-directory:`. A `run` step with no `shell:` already runs under `bash -e`, and adding `-u` or `pipefail` can break the team's command.
- [ ] Set the exporter variables on the step. Both are needed, and the sampler must keep every trace: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Write the capture file outside the build directory, in a path the later steps read.

```yaml
- name: Download Perf Sentinel
  id: download
  continue-on-error: true
  run: |
    set -euo pipefail
    case "$(uname -m)" in
      x86_64) ASSET=perf-sentinel-linux-amd64 ;;
      aarch64|arm64) ASSET=perf-sentinel-linux-arm64 ;;
      *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
    esac
    BASE_URL="https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/releases/download/v${PERF_SENTINEL_VERSION}"
    curl -sSLf -o "$ASSET" "${BASE_URL}/${ASSET}"
    curl -sSLf -o SHA256SUMS.txt "${BASE_URL}/SHA256SUMS.txt"
    echo "asset=$ASSET" >> "$GITHUB_OUTPUT"
- name: Verify and install Perf Sentinel
  id: install
  if: steps.download.outcome == 'success'
  env:
    ASSET: ${{ steps.download.outputs.asset }}
  run: |
    set -euo pipefail
    grep "  ${ASSET}$" SHA256SUMS.txt | sha256sum -c -
    mkdir -p "${GITHUB_WORKSPACE}/bin"
    install -m 0755 "$ASSET" "${GITHUB_WORKSPACE}/bin/perf-sentinel"
    echo "${GITHUB_WORKSPACE}/bin" >> "${GITHUB_PATH}"
    "${GITHUB_WORKSPACE}/bin/perf-sentinel" --version
- name: Integration tests under capture
  run: |
    if [ "${{ steps.install.outcome }}" = "success" ]; then
      perf-sentinel capture --output "${{ runner.temp }}/traces.ndjson" -- <existing test command>
    else
      <existing test command>
    fi
  env:
    OTEL_EXPORTER_OTLP_ENDPOINT: http://localhost:4318
    OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
    OTEL_TRACES_SAMPLER: always_on
```

`<existing test command>` is a placeholder: keep the command the workflow already runs, the same in both branches. A pipeline or an `&&` chain goes in a script, and the script is wrapped.

## Analyze and archive

- [ ] A report-only step after the tests, with no `--ci`, so a gate breach never hides the report. Run it on every branch and keep it even when the tests failed (`if: ${{ !cancelled() }}`).
- [ ] Every step after the test step that should run when the tests fail starts its `if:` with `!cancelled() &&`. An `if:` with no status function gets an implicit `success()`, so a failing test silently skips it. Never use `always()`: it stays true on a cancelled run (manual cancel, `concurrency` with `cancel-in-progress`, `timeout-minutes`), so `analyze` would read a truncated capture and a superseded run could post a stale comment. Wrap the whole condition in `${{ }}`, as in the snippets: a bare `!` at the start of a YAML value is a tag, not a negation. The analyze, artifact, tooling-failure, SARIF and PR comment steps need it, the gate does not, since the job is already red.
- [ ] Give it `id: analyze` and `continue-on-error: true`, as Perf Sentinel's template does. An empty capture makes `analyze` exit `75`, and without the tolerance that would turn every branch red with no gate enabled. Only the optional gate may fail the build. Later steps key off `steps.analyze.outcome`, and a closing step warns when it is not `success`.
- [ ] The commands pass `--config .perf-sentinel.toml`. With no such file `analyze` exits 75, nothing is reported and the gate is skipped, so a run passes while seeing nothing. Create the file first (ask) or drop `--config`, as in `CI wiring` of SKILL.md.
- [ ] Write SARIF and JSON, then HTML from `report`. `analyze` gives only text, SARIF and JSON.
- [ ] Write each file under a `.tmp` name and rename it on success, so a crashed `analyze` leaves no empty file that later steps mistake for a report.
- [ ] Archive the three files with `actions/upload-artifact`. Pin every third-party action to a full commit SHA, with the tag in a comment, and check the SHA upstream with `git ls-remote https://github.com/<owner>/<repo>.git 'refs/tags/<tag>*'`. For an annotated tag that prints two lines, and the commit is the one ending in `^{}`, never the tag object above it.
- [ ] The ack file `.perf-sentinel-acknowledgments.toml` is read from the working directory. Run from the repository root, or pass `--acknowledgments`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.

```yaml
- name: Perf Sentinel analyze
  id: analyze
  if: ${{ !cancelled() }}
  continue-on-error: true
  run: |
    set -euo pipefail
    T="${{ runner.temp }}/traces.ndjson"
    perf-sentinel analyze --input "$T" --config .perf-sentinel.toml --format sarif > findings.sarif.tmp
    mv -f findings.sarif.tmp findings.sarif
    perf-sentinel analyze --input "$T" --config .perf-sentinel.toml --format json > report.json.tmp
    mv -f report.json.tmp report.json
    perf-sentinel report --input "$T" --config .perf-sentinel.toml --output report.html
- uses: actions/upload-artifact@<full commit SHA> # <tag>
  if: ${{ !cancelled() }}
  with:
    name: perf-sentinel
    path: |
      findings.sarif
      report.json
      report.html
- name: Report tooling failure
  if: ${{ !cancelled() && steps.analyze.outcome != 'success' }}
  run: echo "::warning::Perf Sentinel did not produce a report, the gate was skipped"
```

## Showing results in the PR

Perf Sentinel's own template does two things, and the skill proposes the same:

- [ ] **SARIF to Code Scanning** with `github/codeql-action/upload-sarif` (`category: perf-sentinel`). When the upload goes through, findings show in the Security tab and as annotations on the PR diff when `code_location` is present. Needs `security-events: write`, plus `actions: read` on a private repository. On a private repository Code Scanning may need GitHub Advanced Security, check the plan before proposing it.
- [ ] Perf Sentinel's current SARIF may be rejected by the upload's schema check when it contains findings. That is a limitation of the engine's output, not a mistake in the workflow. The `findings.sarif` archived as an artifact is the reliable copy. Tell the team before promising results in the Security tab.
- [ ] Give the SARIF upload step `if: ${{ !cancelled() && steps.analyze.outcome == 'success' }}` and `continue-on-error: true`. It also fails on a repository without Code Scanning and on a token that cannot write security events. None of these is a performance problem.
- [ ] **Sticky PR comment** built from `report.json` with `jq` (finding counts by severity, `io_waste_ratio`, `quality_gate.passed`) and posted with `marocchino/sticky-pull-request-comment`. Needs `pull-requests: write`. It is a third-party action, so name it and pin it before asking.
- [ ] Give the comment steps `if: ${{ !cancelled() && github.event_name == 'pull_request' && ... }}`, and give the post step `continue-on-error: true`. A pull request from a fork gets a read-only token, so the post fails there. The fork limitation is described under the CI recipes link below.
- [ ] Say the permissions out loud (`security-events: write`, `actions: read` on a private repository, `pull-requests: write`) and ask before editing the workflow's `permissions:` block. Keep `contents: read`.
- [ ] To run the workflow locally (`act` or a similar runner), pass a dummy `GITHUB_TOKEN` and no `gh` credentials. Otherwise the comment and SARIF steps act on the real repository: `act` picks up the `gh` token by itself and takes the repository from the `origin` remote.
- [ ] No other integration. The HTML dashboard through GitHub Pages is an opt-in recipe in the Perf Sentinel docs: mention it, do not set it up.

## Optional gate

The gate is the team's choice. Recommend it on pull requests only, show the change, never turn it on yourself.

- [ ] Perf Sentinel's template reads the result already on disk: on a PR, a step fails when `jq -r '.quality_gate.passed' report.json` is not `true`. Exit codes of `analyze --ci` give the same verdict if the team prefers: `1` for a breach, `75` for a tooling error, [perf-sentinel.md](../perf-sentinel.md), section `Exit codes`.
- [ ] On the main branch, the template only prints a `::warning::` when the gate would have failed, and the run stays green.
- [ ] A tooling failure (download, `analyze` crash) is never a breach. The gate step above runs only when `steps.analyze.outcome == 'success'`. The download step tolerates a failed download, the verify step never tolerates a checksum mismatch.
- [ ] To block merges, the team marks the job as a required status check in branch protection. That is a repository setting, say so and leave it to them.

```yaml
- name: Quality gate (pull requests only)
  if: github.event_name == 'pull_request' && steps.analyze.outcome == 'success'
  run: |
    [ "$(jq -r '.quality_gate.passed' report.json)" = "true" ] \
      || { echo "::error::Perf Sentinel quality gate failed"; exit 1; }
```

## Links

- Perf Sentinel, CI recipes and the GitHub Actions template: https://perf-sentinel.dev/docs/CI#ci-integration-recipes
- Perf Sentinel, gate philosophy: https://perf-sentinel.dev/docs/CI#quality-gate-philosophy
- Perf Sentinel, tooling failures versus breaches: https://perf-sentinel.dev/docs/CI#tooling-failures-vs-quality-gate-breaches
- Perf Sentinel, where SARIF shows up: https://perf-sentinel.dev/docs/CI#where-sarif-surfaces-in-each-provider
- Perf Sentinel, acknowledgments: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS
- GitHub, workflow syntax: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub, workflow commands (`GITHUB_PATH`): https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands
- GitHub, `GITHUB_TOKEN` permissions: https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication
- GitHub, uploading SARIF to Code Scanning: https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github
- GitHub, `actions/upload-artifact`: https://github.com/actions/upload-artifact

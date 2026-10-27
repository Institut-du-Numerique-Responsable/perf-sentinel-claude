# GitHub Actions

Status: written from official docs, not yet tried

## Detecting it

- [ ] Workflow files in `.github/workflows/*.yml`. Find the job and the step that runs the integration tests.
- [ ] A Perf Sentinel step already there: `grep -rn "perf-sentinel" .github/workflows`. If it exists, extend it, never add a second one.
- [ ] A reusable workflow or composite action (`uses: ./...` or `uses: <org>/<repo>/.github/workflows/...`) around the test step: if you cannot read it, load `other.md` as well.

## Wrapping the test step

- [ ] Install Perf Sentinel in its own step before the test step, from the official release with the SHA256 check, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). Use the current release tag in a workflow variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file.
- [ ] The release asset lands in the current directory as `perf-sentinel-linux-amd64`, not on `PATH`. Install it as `bin/perf-sentinel` under the workspace and append that directory to `$GITHUB_PATH`, as Perf Sentinel's template does. A path added to `$GITHUB_PATH` applies to the later steps only, never to the step that adds it, so the install cannot share a step with the tests.
- [ ] Prefix the existing test command with `capture`. Never add a second step that reruns the suite.
- [ ] Set the exporter variables on the step. Both are needed, and the sampler must keep every trace: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Write the capture file outside the build directory, in a path the later steps read.

```yaml
- name: Install Perf Sentinel
  run: |
    set -euo pipefail
    BASE_URL="https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/releases/download/v${PERF_SENTINEL_VERSION}"
    curl -sSLf -o perf-sentinel-linux-amd64 "${BASE_URL}/perf-sentinel-linux-amd64"
    curl -sSLf -o SHA256SUMS.txt "${BASE_URL}/SHA256SUMS.txt"
    grep 'perf-sentinel-linux-amd64' SHA256SUMS.txt | sha256sum -c -
    mkdir -p "${GITHUB_WORKSPACE}/bin"
    install -m 0755 perf-sentinel-linux-amd64 "${GITHUB_WORKSPACE}/bin/perf-sentinel"
    echo "${GITHUB_WORKSPACE}/bin" >> "${GITHUB_PATH}"
- name: Integration tests under capture
  run: |
    set -euo pipefail
    perf-sentinel capture --output "${{ runner.temp }}/traces.ndjson" \
      -- <existing test command>
  env:
    OTEL_EXPORTER_OTLP_ENDPOINT: http://localhost:4318
    OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
    OTEL_TRACES_SAMPLER: always_on
```

`<existing test command>` is a placeholder: keep the command the workflow already runs. A pipeline or an `&&` chain goes in a script, and the script is wrapped.

## Analyze and archive

- [ ] A report-only step after the tests, with no `--ci`, so a gate breach never hides the report. Run it on every branch and keep it even when the tests failed (`if: always()`).
- [ ] Give it `id: analyze` and `continue-on-error: true`, as Perf Sentinel's template does. An empty capture makes `analyze` exit `75`, and without the tolerance that would turn every branch red with no gate enabled. Only the optional gate may fail the build. Later steps key off `steps.analyze.outcome`, and a closing step warns when it is not `success`.
- [ ] The commands pass `--config .perf-sentinel.toml`. With no such file `analyze` exits 75, nothing is reported and the gate is skipped, so a run passes while seeing nothing. Create the file first (ask) or drop `--config`, as in `CI wiring` of SKILL.md.
- [ ] Write SARIF and JSON, then HTML from `report`. `analyze` gives only text, SARIF and JSON.
- [ ] Write each file under a `.tmp` name and rename it on success, so a crashed `analyze` leaves no empty file that later steps mistake for a report.
- [ ] Archive the three files with `actions/upload-artifact`. Pin every third-party action to a full commit SHA, with the tag in a comment, and check the SHA upstream.
- [ ] The ack file `.perf-sentinel-acknowledgments.toml` is read from the working directory. Run from the repository root, or pass `--acknowledgments`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.

```yaml
- name: Perf Sentinel analyze
  id: analyze
  if: always()
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
  if: always()
  with:
    name: perf-sentinel
    path: |
      findings.sarif
      report.json
      report.html
- name: Report tooling failure
  if: always() && steps.analyze.outcome != 'success'
  run: echo "::warning::Perf Sentinel did not produce a report, the gate was skipped"
```

## Showing results in the PR

Perf Sentinel's own template does two things, and the skill proposes the same:

- [ ] **SARIF to Code Scanning** with `github/codeql-action/upload-sarif` (`category: perf-sentinel`). Findings show in the Security tab and as annotations on the PR diff when `code_location` is present. Needs `security-events: write`. On a private repository Code Scanning may need GitHub Advanced Security, check the plan before proposing it.
- [ ] **Sticky PR comment** built from `report.json` with `jq` (finding counts by severity, `io_waste_ratio`, `quality_gate.passed`) and posted with `marocchino/sticky-pull-request-comment`. Needs `pull-requests: write`. It is a third-party action, so name it and pin it before asking.
- [ ] Say both permissions out loud and ask before editing the workflow's `permissions:` block. Keep `contents: read`.
- [ ] A pull request from a fork gets a read-only token, so the comment step fails there. The template marks it `continue-on-error: true`. The fork limitation is described under the CI recipes link below.
- [ ] No other integration. The HTML dashboard through GitHub Pages is an opt-in recipe in the Perf Sentinel docs: mention it, do not set it up.

## Optional gate

The gate is the team's choice. Recommend it on pull requests only, show the change, never turn it on yourself.

- [ ] Perf Sentinel's template reads the result already on disk: on a PR, a step fails when `jq -r '.quality_gate.passed' report.json` is not `true`. Exit codes of `analyze --ci` give the same verdict if the team prefers: `1` for a breach, `75` for a tooling error, [perf-sentinel.md](../perf-sentinel.md), section `Exit codes`.
- [ ] On the main branch, the template only prints a `::warning::` when the gate would have failed, and the run stays green.
- [ ] A tooling failure (download, `analyze` crash) is never a breach. The gate step above runs only when `steps.analyze.outcome == 'success'`. The template tolerates a failed download too, but never a checksum mismatch.
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

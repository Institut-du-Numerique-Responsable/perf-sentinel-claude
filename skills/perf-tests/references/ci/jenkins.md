# Jenkins

Status: tried end-to-end

Tried: a Pipeline job on Jenkins LTS in Docker, native arm64 Debian agent, Maven wrapper with Failsafe and Testcontainers, a branch build, failing tests, the gate with and without an N+1 on a simulated pull request build, a missing config file and a failed download. Not tried: a real pull request (`CHANGE_ID` came from a build parameter on a plain Pipeline job, not a Multibranch Pipeline with an SCM), a separate agent (the builds ran with `agent any` on the controller's built-in node), the `amd64` asset on a native amd64 agent (it ran once, under emulation), a checksum mismatch (only a failed download was run), a Windows agent, Warnings NG `qualityGates`, the HTML Publisher recipe.

## Detecting it

- [ ] A `Jenkinsfile` at the root, declarative or scripted. Find the stage that runs the integration tests.
- [ ] A Perf Sentinel stage already there: `grep -n "perf-sentinel" Jenkinsfile`. If it exists, extend it.
- [ ] Whether the job is a Multibranch Pipeline. Only that type sets `env.CHANGE_ID` on pull request builds. In a classic single-branch pipeline it is always null and a PR-only gate never runs.
- [ ] A shared library (`@Library(...)`) or a company pipeline function wrapping the stages: if you cannot read it, load `other.md` as well and describe the result to obtain, never the library's API.

## Wrapping the test step

- [ ] The agent needs the `perf-sentinel` binary before the tests. Install it from the official release with the SHA256 check, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). Use the current release tag in an `environment` variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file.
- [ ] The asset must match the agent architecture: `perf-sentinel-linux-amd64` when `uname -m` prints `x86_64`, `perf-sentinel-linux-arm64` when it prints `aarch64`. The snippet picks it from `uname -m` inside the download step, so an unknown architecture is a tooling failure, never a red build. The release URL takes the tag with its `v`: `releases/download/v${PERF_SENTINEL_VERSION}`.
- [ ] Rename the asset to `perf-sentinel`, make it executable, and call it as `./perf-sentinel` in every stage, `capture` included, as Perf Sentinel's template does. Use one form throughout, never a bare `perf-sentinel` next to `./perf-sentinel`.
- [ ] `sh` starts in the workspace root. When the test command runs inside a `dir(...)` block (a Maven wrapper in a subfolder, for example), a relative path resolves against that folder: write `"$WORKSPACE/perf-sentinel"` and `"$WORKSPACE/$PERF_SENTINEL_TRACES"` there.
- [ ] Jenkins reuses the workspace between builds of a job, and a checkout does not delete untracked files. Delete the previous binary, capture and reports first, as in the install snippet. Otherwise, when a step fails, the previous build's reports are archived as this build's, and on a pull request build the `fileExists` guard lets the gate run and turn a tooling failure red.
- [ ] Wrap only the download in `catchError`. Run the checksum check outside it, only when both files arrived: a mismatch must fail the build.

```groovy
// pipeline level
environment {
    PERF_SENTINEL_VERSION = '<current release, without the v>'
    PERF_SENTINEL_TRACES  = 'perf-sentinel-out/traces.ndjson'
}

stage('Install Perf Sentinel') {
    steps {
        // a reused workspace keeps the previous build's files
        sh 'rm -f perf-sentinel perf-sentinel-linux-* perf-sentinel.asset SHA256SUMS.txt "$PERF_SENTINEL_TRACES" results.sarif report.json report.html'
        catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
            sh '''
                set -eu
                case "$(uname -m)" in
                    x86_64) ASSET=perf-sentinel-linux-amd64 ;;
                    aarch64|arm64) ASSET=perf-sentinel-linux-arm64 ;;
                    *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
                esac
                BASE_URL="https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/releases/download/v${PERF_SENTINEL_VERSION}"
                curl -sSLf -o "$ASSET" "$BASE_URL/$ASSET"
                curl -sSLf -o SHA256SUMS.txt "$BASE_URL/SHA256SUMS.txt"
                echo "$ASSET" > perf-sentinel.asset
            '''
        }
        // outside catchError: a checksum mismatch fails the build
        script {
            if (fileExists('perf-sentinel.asset') && fileExists('SHA256SUMS.txt')) {
                sh '''
                    set -eu
                    ASSET=$(cat perf-sentinel.asset)
                    grep "$ASSET" SHA256SUMS.txt | sha256sum -c -
                    mv -f "$ASSET" perf-sentinel
                    chmod +x perf-sentinel
                    ./perf-sentinel --version
                '''
            }
        }
    }
}
```

- [ ] Prefix the existing test command in its `sh` step with `capture`. Never add a second stage that reruns the suite.
- [ ] Wrap the `sh` step in `catchError(buildResult: 'FAILURE', stageResult: 'FAILURE')`, as in the snippet. Without it a failing test stops the pipeline before the analyze stage and the report is lost. The build still ends red.
- [ ] Run the bare test command when the binary is missing, as in the snippet. After a failed download, `capture` would not start, the tests would not run and the build would turn red for a tooling problem.
- [ ] Set the exporter variables for that step: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Write the capture file outside the build directory. A `clean` goal (`mvn clean verify`) deletes `target/`, under the listener's feet. Use a folder the build never cleans, such as `perf-sentinel-out/` under the workspace root, and read it from the later stages.
- [ ] The template pins an agent label (`linux`) because it uses `curl` and `sha256sum`. Keep the agent the test stage already uses.

```groovy
stage('Integration tests') {
    environment {
        OTEL_EXPORTER_OTLP_ENDPOINT = 'http://localhost:4318'
        OTEL_EXPORTER_OTLP_PROTOCOL = 'http/protobuf'
        OTEL_TRACES_SAMPLER         = 'always_on'
    }
    steps {
        // the build stays red on failing tests, the pipeline goes on to the analyze stage
        catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
            // no binary after a failed download: run the tests anyway, the build is already unstable
            sh '''
                if [ -x ./perf-sentinel ]; then
                    ./perf-sentinel capture --output "$PERF_SENTINEL_TRACES" -- <existing test command>
                else
                    <existing test command>
                fi
            '''
        }
    }
}
```

`<existing test command>` is a placeholder: keep the command the stage already runs, the same in both branches.

## Analyze and archive

- [ ] A report-only stage after the tests, with no `--ci`. Wrap it in `catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE')` so a tooling problem marks the build unstable and never red.
- [ ] The commands pass `--config .perf-sentinel.toml`. With no such file `analyze` exits 75 and nothing is reported, so create the file first (ask) or drop `--config`, as in `CI wiring` of SKILL.md.
- [ ] The `sh` step runs `/bin/sh`, which is dash on Debian and Ubuntu. Dash rejects `set -o pipefail` with `Illegal option -o pipefail` on Debian 12 and Ubuntu 24.04, and accepts it on Debian 13. The install and analyze snippets need no `pipefail`, so they use `set -eu`: the analyze block has no pipe, and in the install block `sha256sum -c -` fails on its own when `grep` finds no line. The test step sets nothing: Jenkins already runs `sh` with `-xe`, and `-u` could break the team's command on an unset variable. If you add a pipe whose failure matters, start the script with `#!/bin/bash` and use `set -euo pipefail`.
- [ ] SARIF and JSON from `analyze --format`, HTML from `report`. Write each under a `.tmp` name and rename on success, so a crash leaves no empty file that `fileExists` mistakes for a report.
- [ ] In `post { always { ... } }`, `archiveArtifacts` the files with `allowEmptyArchive: true`.
- [ ] The ack file `.perf-sentinel-acknowledgments.toml` is read from the working directory. Run from the workspace root, or pass `--acknowledgments`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.

```groovy
stage('Perf Sentinel analyze') {
    steps {
        catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
            sh '''
                set -eu
                ./perf-sentinel analyze --input "$PERF_SENTINEL_TRACES" --config .perf-sentinel.toml --format sarif > results.sarif.tmp
                mv -f results.sarif.tmp results.sarif
                ./perf-sentinel analyze --input "$PERF_SENTINEL_TRACES" --config .perf-sentinel.toml --format json > report.json.tmp
                mv -f report.json.tmp report.json
                ./perf-sentinel report --input "$PERF_SENTINEL_TRACES" --config .perf-sentinel.toml --output report.html
            '''
        }
    }
}
```

## Showing results in the PR

- [ ] **Warnings Next Generation** reads the SARIF with `recordIssues(enabledForFailure: true, tools: [sarif(pattern: 'results.sarif', id: 'perf-sentinel', name: 'perf-sentinel')])` in `post { always }`. It gives an issue tree and a trend chart per build.
- [ ] The plugin must be installed, in a version that has the `sarif` tool. Perf Sentinel's template names the minimum in its header, and older versions throw `NoSuchMethodError`. Installing a plugin is a Jenkins admin action: say so and ask who can do it.
- [ ] No token. The issue tree appears on the build page. Whether a PR status links to it depends on the branch source plugin of the team's SCM, which is theirs to configure.
- [ ] No other integration. The interactive HTML through the HTML Publisher plugin is an opt-in recipe in the Perf Sentinel docs: mention it, do not set it up. The `report.html` file is archived either way.

## Optional gate

The gate is the team's choice. Recommend it on pull request builds only, show the change, never turn it on yourself.

- [ ] A dedicated stage that re-runs `./perf-sentinel analyze --ci --input ... --config ...`. Exit `1` fails the stage, `75` is a tooling error: [perf-sentinel.md](../perf-sentinel.md), section `Exit codes`.
- [ ] Guard it with a `when` block that requires both `env.CHANGE_ID != null` and `fileExists('results.sarif')`, as in the snippet. Branch builds skip it and stay green. The `fileExists` check keeps a tooling failure from showing as a breach.
- [ ] Warnings NG can add a second check with `qualityGates`. Perf Sentinel's template applies it only when `env.CHANGE_ID != null`, so the post block does not reintroduce blocking on branch builds.
- [ ] A checksum mismatch must always fail the build: the install snippet keeps the verification outside `catchError`.
- [ ] To block merging, the team makes the Jenkins check required in the branch protection of its SCM. That setting is theirs.

```groovy
stage('Quality gate (PR only)') {
    when {
        allOf {
            expression { env.CHANGE_ID != null }
            expression { fileExists('results.sarif') }
        }
    }
    steps {
        sh './perf-sentinel analyze --ci --input "$PERF_SENTINEL_TRACES" --config .perf-sentinel.toml'
    }
}
```

## Links

- Perf Sentinel, CI recipes and the Jenkins template: https://perf-sentinel.dev/docs/CI#ci-integration-recipes
- Perf Sentinel, gate philosophy: https://perf-sentinel.dev/docs/CI#quality-gate-philosophy
- Perf Sentinel, tooling failures versus breaches: https://perf-sentinel.dev/docs/CI#tooling-failures-vs-quality-gate-breaches
- Perf Sentinel, Jenkins HTML Publisher recipe: https://perf-sentinel.dev/docs/CI#interactive-report-via-jenkins-html-publisher
- Perf Sentinel, acknowledgments: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS
- Jenkins, Pipeline syntax and the Jenkinsfile: https://www.jenkins.io/doc/book/pipeline/jenkinsfile/
- Jenkins, Multibranch Pipeline and `CHANGE_ID`: https://www.jenkins.io/doc/book/pipeline/multibranch/
- Jenkins, `archiveArtifacts` and core steps: https://www.jenkins.io/doc/pipeline/steps/core/
- Warnings Next Generation plugin: https://plugins.jenkins.io/warnings-ng/

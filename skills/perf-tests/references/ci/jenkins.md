# Jenkins

Status: written from official docs, not yet tried

## Detecting it

- [ ] A `Jenkinsfile` at the root, declarative or scripted. Find the stage that runs the integration tests.
- [ ] A Perf Sentinel stage already there: `grep -n "perf-sentinel" Jenkinsfile`. If it exists, extend it.
- [ ] Whether the job is a Multibranch Pipeline. Only that type sets `env.CHANGE_ID` on pull request builds. In a classic single-branch pipeline it is always null and a PR-only gate never runs.
- [ ] A shared library (`@Library(...)`) or a company pipeline function wrapping the stages: if you cannot read it, load `other.md` as well and describe the result to obtain, never the library's API.

## Wrapping the test step

- [ ] The agent needs the `perf-sentinel` binary before the tests. Install it from the official release with the SHA256 check, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). Use the current release tag in an `environment` variable such as `PERF_SENTINEL_VERSION`, never `latest`, and write no number from this file.
- [ ] The release asset lands in the workspace as `perf-sentinel-linux-amd64`. Rename it to `perf-sentinel`, make it executable, and call it as `./perf-sentinel` in every stage, `capture` included, as Perf Sentinel's template does. `sh` starts in the workspace root, so keep the calls out of a `dir(...)` block or use an absolute path there. Use one form throughout, never a bare `perf-sentinel` next to `./perf-sentinel`.
- [ ] Prefix the existing test command in its `sh` step with `capture`. Never add a second stage that reruns the suite.
- [ ] Wrap the `sh` step in `catchError(buildResult: 'FAILURE', stageResult: 'FAILURE')`, as in the snippet. Without it a failing test stops the pipeline before the analyze stage and the report is lost. The build still ends red.
- [ ] Set the exporter variables for that step: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] Write the capture file outside the build directory. A `clean` goal (`mvn clean verify`) deletes `target/`, under the listener's feet. Use a folder the build never cleans, such as `perf-sentinel-out/` under the workspace root, and read it from the later stages.
- [ ] The template pins an agent label (`linux`) because it uses `curl` and `sha256sum`. Keep the agent the test stage already uses.

```groovy
// pipeline level, so every stage reads the same path
environment {
    PERF_SENTINEL_TRACES = 'perf-sentinel-out/traces.ndjson'
}

stage('Integration tests') {
    environment {
        OTEL_EXPORTER_OTLP_ENDPOINT = 'http://localhost:4318'
        OTEL_EXPORTER_OTLP_PROTOCOL = 'http/protobuf'
        OTEL_TRACES_SAMPLER         = 'always_on'
    }
    steps {
        // the build stays red on failing tests, the pipeline goes on to the analyze stage
        catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
            sh './perf-sentinel capture --output "$PERF_SENTINEL_TRACES" -- <existing test command>'
        }
    }
}
```

`<existing test command>` is a placeholder: keep the command the stage already runs.

## Analyze and archive

- [ ] A report-only stage after the tests, with no `--ci`. Wrap it in `catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE')` so a tooling problem marks the build unstable and never red.
- [ ] The commands pass `--config .perf-sentinel.toml`. With no such file `analyze` exits 75 and nothing is reported, so create the file first (ask) or drop `--config`, as in `CI wiring` of SKILL.md.
- [ ] The `sh` step runs `/bin/sh`, which is dash on Debian and Ubuntu and rejects `set -o pipefail`. The block has no pipe, so it uses `set -eu`. If you add a pipe, start the script with `#!/bin/bash` and use `set -euo pipefail`.
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
- [ ] A checksum mismatch must always fail the build. Wrap only the download in `catchError`, never the verification.
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

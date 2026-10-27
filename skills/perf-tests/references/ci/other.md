# Other CI or an internal layer

Status: written from official docs, not yet tried

## Detecting it

- [ ] The CI is not GitHub Actions, GitLab CI, Jenkins, Azure DevOps or CircleCI (Bitbucket Pipelines, Drone, TeamCity, Buildkite, a self-made runner).
- [ ] Or it is one of those, but the pipeline goes through a layer you cannot read: a shared library, a company template, a reusable workflow, an orb, an `include` from a private project.
- [ ] Say it plainly: "the CI goes through a layer I cannot read". Do not guess its API, its parameters or its conventions, and do not write a file that calls it.

## Wrapping the test step

Four results to obtain. The pipeline's own mechanism for each is the developer's to name.

- [ ] **Capture around the tests.** The existing test command runs once, prefixed with `perf-sentinel capture --output <file> -- <command>`. No second job or step reruns the suite. The exporter variables are set for it: [perf-sentinel.md](../perf-sentinel.md), section `capture`.
- [ ] **Analyze and archive.** After the tests, on every branch, even when the tests failed: `analyze` in report-only mode writes SARIF and JSON, `report` writes the HTML, and the three files are kept with the build.
- [ ] **Ack file honored.** `.perf-sentinel-acknowledgments.toml`, versioned in the repository, is read from the working directory of `analyze`. Entry template: [perf-sentinel.md](../perf-sentinel.md), section `Acknowledgment entry`.
- [ ] **Optional gate.** `analyze --ci` runs on pull request builds only, so exit `1` fails that build and nothing fails on the main branch. The team decides, and the skill does not turn it on.

The binary must be on the agent before `capture`: official release, SHA256 check, current release tag, as in the `Install` section of [perf-sentinel.md](../perf-sentinel.md). The binary must also be callable from the later steps: most CIs start each step in a new shell, so a `PATH` change needs the CI's own mechanism, or an absolute path in every call. If the agents have no network access to GitHub releases, that is a question for the owner of the layer.

## Analyze and archive

- [ ] Report-only commands must not fail the build on their own: an empty capture makes `analyze` exit `75`, so tolerate that code here and let only the optional gate fail. The commands, in this shape: `perf-sentinel analyze --input <file> --config .perf-sentinel.toml --format sarif`, the same with `--format json`, and `perf-sentinel report --input <file> --config .perf-sentinel.toml --output report.html`. Only `analyze --ci` sets the gate exit code. `report` exits `0` even when the gate fails.
- [ ] `--config .perf-sentinel.toml` needs the file. With none, `analyze` exits 75 and the run passes while seeing nothing. Create the file first (ask) or drop `--config`, as in `CI wiring` of SKILL.md.
- [ ] Exit codes to branch on: `1` is a breach, `75` is a tooling error, never a breach, [perf-sentinel.md](../perf-sentinel.md), section `Exit codes`. A pipeline that treats every non-zero code alike blocks on a download failure.
- [ ] Where the pipeline offers a way to keep files with the build, use it for the three outputs. If it has none, say so.

## Showing results in the PR

- [ ] Only what the CI already has. Perf Sentinel documents SARIF to GitHub Code Scanning, a GitLab Code Quality report and Jenkins Warnings NG. For any other CI, archive the files and stop there.
- [ ] If the layer already reads SARIF or has a code-quality report, say so and ask whether to feed it. If it needs a token or a permission, name it and let the team grant it.
- [ ] The CI never feeds the Perf Sentinel Hub.

## Optional gate

- [ ] Describe the gate as a result: "on pull request builds only, run `analyze --ci` and fail on exit `1`". Show it as a command, not as a pipeline change.
- [ ] Ask which condition tells a pull request build from a branch build in this CI.

## Ask the developer who owns the layer

When the layer is unreadable, end the CI part of the summary with one question, and write nothing to the CI until it is answered:

- [ ] Who owns the shared library or template (a platform team, a CI team)?
- [ ] Does it already offer a step, a parameter or an extension point for the four results above, and what is it called?
- [ ] If not, would that team accept a change, or should the project's own pipeline file wrap the test command with `capture` directly?

Report the four results with their status in the summary: obtained, already provided by the layer, or waiting for the owner's answer.

## Links

- Perf Sentinel, CI mode and exit codes: https://perf-sentinel.dev/docs/CI#ci-mode-batch-analysis
- Perf Sentinel, CI recipes: https://perf-sentinel.dev/docs/CI#ci-integration-recipes
- Perf Sentinel, gate philosophy: https://perf-sentinel.dev/docs/CI#quality-gate-philosophy
- Perf Sentinel, acknowledgments: https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS

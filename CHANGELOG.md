# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Windows, from an end-to-end trial of both skills on Windows 11: `capture --` wraps `mvnw.cmd` or `gradlew.bat`, since the binary cannot start `./mvnw` (`os error 193`). In Git Bash, `docker run` needs `MSYS_NO_PATHCONV=1` and a `C:/...` mount source, or the capture path is rewritten and nothing is written. `prod-findings` falls back to `python` then `py -3` when `python3` is the Microsoft Store alias, and warns that the page write asks for approval. The terminal UI container is quit with `q`, not by closing the terminal.

## [0.3.2] - 2026-10-30

### Added

- README: how to turn on auto-update, which Claude Code leaves off for a third-party marketplace, for one person (`/plugin`, **Marketplaces**) or a whole team (`extraKnownMarketplaces` with `autoUpdate` in the repository's `.claude/settings.json`), and how to read the installed version.

## [0.3.1] - 2026-10-30

### Changed

- Local run modes, from an end-to-end trial on a Spring Boot service: no Intel Mac asset (use Docker), the macOS quarantine attribute on a browser download, an approval per call for a binary called by its path, and the mount to use when the capture file sits outside the repository. The Spring Boot reference records the trial.

## [0.3.0] - 2026-10-30

### Added

- `perf-tests` offers three local run modes when the binary is missing: on the `PATH`, in a folder of the developer's choice, or the Docker image (Docker Hub or GHCR), with the background `capture` form Docker needs. Tried with the 0.38.0 image on Docker Desktop for macOS: `docker stop` flushes the capture, `analyze` and the terminal UI run in the container.
- A local run ends by asking how to read the results: the terminal UI command for the developer to type, or the HTML report, which the skill renders after a yes and hands over as a file path. Both tried in the container.

## [0.2.0] - 2026-10-29

### Added

- `prod-findings` skill: reads production findings from Perf Sentinel Hub through the `perf-sentinel` CLI, ranks them by avoidable I/O (N+1 and redundant first, then slow by risk, then structural), and either stops at the ranking or helps fix them in small batches, each proven by a `perf-tests` non-regression test. It asks before every change, and can rank a JSON file saved from `perf-sentinel hub findings --format json`. The window defaults to the last 7 complete UTC days and can be given as an argument. It needs the CLI 0.37.0 or later signed in to Hub 0.8.6 or later for volumes, and Python 3. Tried on a local Hub 0.8.6 with perf-sentinel 0.37.1: ranking, lower bounds and the no-volume case.

### Changed

- `perf-tests` accepts finding signatures (`/perf-sentinel:perf-tests bugfix <signature> …`) and reads them from the Hub when the CLI is signed in.
- The plugin and marketplace descriptions mention both skills.

## [0.1.1] - 2026-10-28

### Changed

- The GitHub Actions and GitLab CI references were tried end-to-end, locally with `act` and `gitlab-ci-local`, and fixed: release asset picked by architecture, tests still run when the download fails, report steps skipped on a cancelled GitHub run, a rejected SARIF upload tolerated, the GitLab install moved to a `.pre` job, and a stable Code Quality fingerprint.
- The CI references follow Perf Sentinel 0.35.0: its SARIF passes the GitHub upload schema check, and the GitLab Code Quality line is 1 or more, as in the engine template.
- The `perf-tests` description is shorter (919 to 559 characters) and keeps the rules for when to start and when to propose the skill.

## [0.1.0] - 2026-10-27

### Added

- Claude Code plugin and single-plugin marketplace, installable with `/plugin marketplace add Institut-du-Numerique-Responsable/perf-sentinel-claude`.
- `perf-tests` skill: reads the current diff, proposes scenarios, then writes performance integration tests that run under Perf Sentinel and, on request, wires them into CI. It asks before every change.
- References for the `perf-sentinel` CLI and for fix safety, ten stack references (.NET, Python, Go, Node.js, PHP, Ruby, Rust, Spring Boot, Quarkus, Micronaut) and six CI references (GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, other). .NET, Python, Spring Boot and Jenkins were tried end-to-end.
- Eval suite under `evals/` with fixtures, run by `claude plugin eval`.
- Structural checker `scripts/check_plugin.py`, with unit tests, and a CI workflow that runs both.
- License: Apache-2.0 for code, CC BY 4.0 for the skill, references and documentation, with a `NOTICE` and a `CITATION.cff`.

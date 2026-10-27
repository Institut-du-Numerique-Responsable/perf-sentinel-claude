# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-10-27

### Added

- Claude Code plugin and single-plugin marketplace, installable with `/plugin marketplace add Institut-du-Numerique-Responsable/perf-sentinel-claude`.
- `perf-tests` skill: reads the current diff, proposes scenarios, then writes performance integration tests that run under Perf Sentinel and, on request, wires them into CI. It asks before every change.
- References for the `perf-sentinel` CLI and for fix safety, ten stack references (.NET, Python, Go, Node.js, PHP, Ruby, Rust, Spring Boot, Quarkus, Micronaut) and six CI references (GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, other). .NET, Python, Spring Boot and Jenkins were tried end-to-end.
- Eval suite under `evals/` with fixtures, run by `claude plugin eval`.
- Structural checker `scripts/check_plugin.py`, with unit tests, and a CI workflow that runs both.
- License: Apache-2.0 for code, CC BY 4.0 for the skill, references and documentation, with a `NOTICE` and a `CITATION.cff`.

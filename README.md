# Perf Sentinel plugin for Claude Code

This plugin adds a skill that writes performance integration tests for your current change.
The tests run under [Perf Sentinel](https://perf-sentinel.dev), which flags N+1, redundant and slow I/O before it reaches production.
It works from the diff, picks the instrumentation for your stack and wires the check into your CI.

## Install

```
/plugin marketplace add Institut-du-Numerique-Responsable/perf-sentinel-claude-plugin
/plugin install perf-sentinel@perf-sentinel
```

## Usage

```
/perf-sentinel:perf-tests [precision]
```

The optional precision narrows what to test, for example a module or an endpoint.

## Coverage

Stacks: .NET, Python, Go, Node.js, PHP, Ruby, Rust and Java (Spring Boot, Quarkus, Micronaut).
CI systems: GitHub Actions, GitLab CI, Jenkins, Azure DevOps and CircleCI, plus a generic fallback for any other.

The .NET and Python references were tried end-to-end. The others are written from the official documentation and have not been tried yet, so each says so in its `Status:` line.

The skill asks before every change and runs nothing in CI by itself. It only writes the CI step, and you decide when it runs.

More about the tool at https://perf-sentinel.dev.

## Development

```
python3 -m unittest scripts/test_check_plugin.py
python3 scripts/check_plugin.py .
claude plugin validate .
claude plugin eval . --scaffold --trust-plugin --threshold 0.66 --no-publish --judge-model sonnet --allow-tools "Bash(git diff:*)" "Bash(git log:*)" "Bash(git status:*)" "Bash(git merge-base:*)" Write Edit
```

Grant `Write` and `Edit` at run level, otherwise the no-edit graders cannot fail. Keep concurrency low (`-j 1` or `-j 2`) to avoid process-limit failures.

## License

Code: **Apache-2.0**. Skill, references and documentation: **CC BY 4.0**. Code examples in the references, such as CI snippets, may also be used under Apache-2.0. See the [license scope](LICENSE) and the [credits](skills/perf-tests/NOTICE).

© 2026 Institut du Numérique Responsable. Perf Sentinel itself is a separate work under AGPL-3.0-only.

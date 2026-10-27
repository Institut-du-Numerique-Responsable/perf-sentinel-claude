# Security policy

## Supported versions

Only the latest release of the plugin receives security fixes.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public issues, discussions or pull requests.**

Report them privately through GitHub's private vulnerability reporting:

1. Open the [Security tab](https://github.com/Institut-du-Numerique-Responsable/perf-sentinel-claude/security) of this repository.
2. Click **Report a vulnerability**.
3. Describe the issue, the affected version, the steps to reproduce and its impact.

You can also open a private advisory directly at
https://github.com/Institut-du-Numerique-Responsable/perf-sentinel-claude/security/advisories/new

## Scope

In scope: anything in this repository that could make an agent following the skill act without the developer's consent, leak a secret, expose a service, or run untrusted code. That covers `SKILL.md`, the references and their CI snippets, the eval fixtures and the scripts.

Out of scope: vulnerabilities in Perf Sentinel itself, which has [its own policy](https://github.com/Institut-du-Numerique-Responsable/perf-sentinel/security/policy), and in Claude Code.

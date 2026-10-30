# Perf Sentinel plugin for Claude Code

This plugin adds two skills for [Perf Sentinel](https://perf-sentinel.dev), which flags N+1, redundant and slow I/O.
`perf-tests` writes performance integration tests for your current change, so the waste is caught before production. It works from the diff, picks the instrumentation for your stack and wires the check into your CI.
`prod-findings` reads the findings of your production services from Perf Sentinel Hub, ranks them by avoidable I/O and helps fix them.

## Install

```
/plugin marketplace add Institut-du-Numerique-Responsable/perf-sentinel-claude
/plugin install perf-sentinel@perf-sentinel
```

### Updates

Claude Code updates a third-party marketplace only when its auto-update is on, and it is off by default. Turn it on once: run `/plugin`, open **Marketplaces**, select `perf-sentinel`, then **Enable auto-update**. Claude Code then updates the plugin in the background during a session and loads the new version at the next launch or on `/reload-plugins`.

For a whole team, declare the marketplace in the repository's `.claude/settings.json`. Once someone accepts the workspace trust dialog for the folder, Claude Code registers the marketplace with auto-update on and loads the plugin. In an untrusted folder it ignores the entry without a message:

```json
{
  "extraKnownMarketplaces": {
    "perf-sentinel": {
      "source": {
        "source": "github",
        "repo": "Institut-du-Numerique-Responsable/perf-sentinel-claude"
      },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "perf-sentinel@perf-sentinel": true
  }
}
```

To update by hand: `claude plugin update perf-sentinel@perf-sentinel`. `claude plugin list` shows the installed version as a 12-character commit, the commit of a release tag.

## Usage

```
/perf-sentinel:perf-tests [precision]
```

The optional precision narrows what to test, for example a module or an endpoint. When the `perf-sentinel` CLI is signed in to a Hub, `/perf-sentinel:perf-tests bugfix <signature> …` takes finding signatures and reads those findings from the Hub.

```
/perf-sentinel:prod-findings [precision]
```

This reads the production findings of the current repository's services from Perf Sentinel Hub, through the `perf-sentinel` CLI. Sign in with `perf-sentinel login --hub <url>`: the token lasts up to 8 hours, then sign in again. The skill ranks the findings of the last 7 complete days by avoidable I/O: N+1 and redundant first, then slow ones by risk, then structural ones. It then works in one of two modes:

- Rank only: it stops at the ranking, a table you can hand to the teams. Say "rank only" in the precision.
- Rank then fix: it proposes batches of one finding type, fixes them on a branch per batch and hands over to `perf-tests` for a non-regression test that proves each fix. It asks before every change, and before acknowledging a finding in the Hub.

The precision narrows the work to a service, a finding type, an environment or a Hub URL. It can also be the path of a JSON file saved with `perf-sentinel hub findings --format json`, which is then ranked without contacting the Hub.

## Coverage

Stacks: .NET, Python, Go, Node.js, PHP, Ruby, Rust and Java (Spring Boot, Quarkus, Micronaut).
CI systems: GitHub Actions, GitLab CI, Jenkins, Azure DevOps and CircleCI, plus a generic fallback for any other.

The .NET, Python and Spring Boot references and the Jenkins, GitHub Actions and GitLab CI references were tried end-to-end (GitHub Actions with `act` and GitLab CI with `gitlab-ci-local`, both run locally), each with a line saying what the trial covered and what it did not. The others are written from the official documentation and have not been tried yet, so each says so in its `Status:` line.

`prod-findings` needs the `perf-sentinel` CLI 0.37.0 or later, signed in to Perf Sentinel Hub 0.8.6 or later for the volumes, and Python 3 for the ranking script. With older versions it still ranks, but every volume is unknown. It has eval cases and has not been tried end-to-end yet.

Both skills ask before every change. `perf-tests` runs nothing in CI by itself: it only writes the CI step, and you decide when it runs.

More about the tool at https://perf-sentinel.dev.

## Development

```
python3 -m unittest scripts/test_check_plugin.py scripts/test_rank.py
python3 scripts/check_plugin.py .
claude plugin validate .
claude plugin eval . --scaffold --trust-plugin --threshold 0.66 --no-publish --judge-model sonnet -j 2 --allow-tools "Bash(git diff:*)" "Bash(git log:*)" "Bash(git status:*)" "Bash(git merge-base:*)" "Bash(python3:*)" Write Edit
```

Grant `Write` and `Edit` at run level, otherwise the no-edit graders cannot fail. Keep concurrency low (`-j 1` or `-j 2`) to avoid process-limit failures.

## License

Code: **Apache-2.0**. Skill, references and documentation: **CC BY 4.0**. Code examples in the references, such as CI snippets, may also be used under Apache-2.0. [LICENSE](LICENSE) holds the Apache-2.0 text, [NOTICE](NOTICE) explains which license covers what and how to credit the work.

© 2026 Institut du Numérique Responsable. Perf Sentinel itself is a separate work under AGPL-3.0-only.

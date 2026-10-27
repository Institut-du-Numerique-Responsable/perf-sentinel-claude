# Perf Sentinel plugin for Claude Code

This plugin adds a skill that writes performance integration tests for your current change.
The tests run under [Perf Sentinel](https://perf-sentinel.dev), which flags N+1, redundant and slow I/O before it reaches production.
It works from the diff, picks the instrumentation for your stack and wires the check into your CI.

## Install

```
/plugin marketplace add robintra/perf-sentinel-claude-plugin
/plugin install perf-sentinel@perf-sentinel
```

## Usage

```
/perf-sentinel:perf-tests [precision]
```

The optional precision narrows what to test, for example a module or an endpoint.

More about the tool at https://perf-sentinel.dev.

## License

AGPL-3.0-only, see [LICENSE](LICENSE).

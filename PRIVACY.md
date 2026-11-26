# Privacy

The Perf Sentinel plugin collects no data. It has no telemetry, no account, no hook and no server of its own. It is made of two skills, text files that Claude Code loads into the session, and one local Python script.

## What leaves your machine

| Call | When | Sent | Received |
|------|------|------|----------|
| `GET https://api.github.com/repos/Institut-du-Numerique-Responsable/perf-sentinel/releases/latest` | Both skills, once per run, to compare the local `perf-sentinel` version with the latest release | An anonymous request: your IP address and the `curl` user agent. No token, no repository data | The latest release's metadata. Offline, the check is skipped and the skill goes on |
| Perf Sentinel Hub, through `perf-sentinel hub findings` and `perf-sentinel hub incidents` | `prod-findings`, and `perf-tests` when the CLI is already signed in to a Hub | Read filters: service, environment, status, time window, signature. The token stored by `perf-sentinel login` travels with them, read by the CLI and never by Claude | The production findings your account may see |
| `perf-sentinel hub ack` | `prod-findings`, only after your explicit yes | The finding's signature, the source and your reason | Writes the acknowledgment on that Hub, in your name |
| GitHub release assets, Docker Hub or `ghcr.io` | Only when `perf-sentinel` is missing or outdated and you accept the install | Standard download requests | The `perf-sentinel` binary and its `SHA256SUMS.txt`, or the Docker image |

The Hub is the one you or your organization run, at the address you give. The plugin contacts no other Hub and no server of the Institut du Numérique Responsable.

## What stays local

- `perf-sentinel capture` and `perf-sentinel analyze` run on your machine. Test traces go to the local `capture` receiver (`127.0.0.1` by default), and the capture file and reports stay on your machine.
- Hub pages are saved to a fresh temporary directory and read by `skills/prod-findings/scripts/rank.py`, which makes no network call.
- The Hub token is never read, printed or passed on a command line by the skills.

## What reaches Claude

As in any Claude Code session, what Claude reads is sent to Anthropic under Anthropic's terms: your code, the diff, command outputs, and for `prod-findings` the ranking of production findings (service, endpoint, query template, code location, volumes). Raw Hub pages are not read into the conversation, only the script's ranking.

Code changes, commits, pushes, pull requests and acknowledgments each wait for your yes.

Questions: open an issue on [GitHub](https://github.com/Institut-du-Numerique-Responsable/perf-sentinel-claude/issues). Security reports: [SECURITY.md](SECURITY.md).

## Confidentialité

Le plugin Perf Sentinel ne collecte aucune donnée : ni télémétrie, ni compte, ni serveur. Il appelle l'API publique de GitHub, sans jeton, pour comparer la version locale de `perf-sentinel` à la dernière publiée. Il lit les constats de production sur le Perf Sentinel Hub que vous lui indiquez, avec le jeton du CLI, que Claude ne lit jamais. Il n'écrit sur ce Hub (`hub ack`) qu'après votre accord. Les traces de test, l'analyse et le classement restent sur votre machine. Ce que Claude lit, dont le classement des constats, part chez Anthropic comme dans toute session Claude Code.

# Agent PTT Announcer — Codex CLI hooks

The same announcer as the [Claude Code plugin](../claude-plugin/), for
OpenAI's Codex CLI: your Mac announces **"Starting: …"** when you submit
a prompt and **"Done."** when Codex finishes, through an
[Agent PTT](https://github.com/arvidsson-geins/agent-ptt) voice channel.

Codex sessions join as `Codex · <folder>`, so Codex gets different
auto-designed voices than Claude Code — you can tell the two agents (and
every project) apart by ear.

## Requirements

- An Agent PTT server running locally: `uv run agent-ptt server start`
- Codex CLI with hooks support
- `python3` on PATH (the hook script is stdlib-only)

## Install

```bash
./codex-plugin/install.sh
```

This writes `~/.codex/hooks.json` (it refuses to overwrite an existing
one and prints the entries for manual merging instead).

### Alternative: inline in `~/.codex/config.toml`

```toml
[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = 'AGENT_PTT_AGENT=Codex python3 "/absolute/path/to/agent-ptt/codex-plugin/announce.py"'
timeout = 60

[[hooks.Stop]]
[[hooks.Stop.hooks]]
type = "command"
command = 'AGENT_PTT_AGENT=Codex python3 "/absolute/path/to/agent-ptt/codex-plugin/announce.py"'
timeout = 60
```

## Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PTT_URL` | `http://localhost:8770` | Agent PTT server |
| `AGENT_PTT_CHANNEL` | `Claude Code` | Channel to announce in |
| `AGENT_PTT_AGENT` | `Claude` | Speaker name prefix (set to `Codex` by the hook entries) |
| `AGENT_PTT_ANNOUNCE` | `1` | Set `0` to disable announcements |

## Behavior notes

- **Never blocks Codex.** The script forks immediately after parsing the
  event, so the hook returns instantly while the announcement happens in
  the background; every failure path exits silently.
- `codex-plugin/announce.py` is byte-identical to the Claude plugin's
  script (a test enforces this) — fix bugs in one place and copy.

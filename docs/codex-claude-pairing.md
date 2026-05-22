# Codex + Claude Pair Workflow

This repo includes `pair.sh`, a per-task loop where Claude implements and Codex reviews:

1. Claude writes a short spec in `.pair/runs/<timestamp>/SPEC.md`.
2. Claude implements against that spec.
3. Codex reviews the uncommitted diff against the spec with `codex exec review --uncommitted`.
4. If Codex returns `fail`, Claude receives the review JSON and fixes the findings.
5. The loop stops when Codex returns `pass` or the max iteration count is reached.

## Run It

```bash
./pair.sh -i 2 "add rate limiting to the login endpoint"
```

Use a clean branch the first few times. By default the script refuses to start with uncommitted work so Codex and Claude do not mix new edits with unrelated local changes. Pass `--allow-dirty` only when you mean it.

The default workhorse mode is interactive Claude Code through `tmux`:

```bash
./pair.sh --claude-mode interactive "your task"
```

You can watch Claude plan, edit, and run checks live when the script prints the session name:

```bash
tmux attach -t pair_YYYYMMDD-HHMMSS_claude
```

If you want a more script-native Claude builder and are okay using Claude Agent SDK credits, use:

```bash
./pair.sh --claude-mode print "your task"
```

## Prereqs

```bash
for b in git jq codex claude tmux; do command -v "$b" || echo "MISSING: $b"; done
```

On macOS, `tmux` is usually:

```bash
brew install tmux
```

Run `codex` and `claude` once manually inside the repo first. Clear login, trust, and permission prompts before expecting an automation loop to behave.

## Best-Practice Updates From Current Docs

- Use `codex exec review --uncommitted` for the Codex audit pass. That keeps Codex focused on the diff instead of spending context on the whole build conversation.
- Keep Codex review sandboxed with `read-only` and non-interactive approvals set to `never`.
- Let Claude do the higher-context work: repo exploration, planning, implementation, and local checks.
- Do not rely on a vague "review my code" prompt. The script makes Claude write a spec, then makes Codex review against explicit acceptance criteria.
- Keep Codex reviewer-only. The review command runs read-only, and the prompt asks for one structured JSON verdict.
- Treat best-practice suggestions as non-blocking unless they reveal a real correctness, security, reliability, or maintainability risk.
- Prefer a clean branch per run. If the loop misfires, you can inspect or revert one task's diff without sorting through unrelated work.
- Keep run artifacts under `.pair/` and out of git.

## Claude Billing/Policy Note

Anthropic's current docs distinguish interactive Claude Code from Agent SDK / `claude -p` usage. Starting June 15, 2026, Agent SDK and `claude -p` usage on eligible subscription plans draws from a separate monthly Agent SDK credit, while interactive Claude Code continues to use normal subscription usage limits.

This script defaults to interactive Claude Code in `tmux` because Claude is the workhorse in this setup. It also provides `--claude-mode print` because `claude -p` is more robust for automation and now has an explicit credit bucket. Choose based on whether you care more about strict scripting reliability or staying in the interactive Claude Code lane.

## What Changes With Claude As Workhorse

Claude sees more context and spends more time/tokens because it plans, edits, and fixes. Codex sees less context because it only reviews the final spec plus uncommitted diff. That is the right default if you trust Claude more for implementation and want Codex to act as a cheaper independent auditor.

The fragile part moves too: the interactive `tmux` automation now waits for Claude to print a completion marker after each work turn. If Claude pauses for a permission prompt or forgets the marker, attach to the tmux session, resolve the prompt, and have Claude print the marker line shown in `.pair/runs/<timestamp>/prompts/claude-work-<n>.md`.

## First Safe Test

```bash
git switch -c codex/pair-loop-smoke-test
./pair.sh -i 1 "add a short note to README explaining how to run tests"
```

Watch the first run in `tmux`. The most common failures are missing `tmux`, stale CLI auth, Claude waiting on a permission/trust prompt, or Claude finishing the code but forgetting the completion marker.

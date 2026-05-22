#!/usr/bin/env bash
set -euo pipefail

MAX_ITERS=2
REPO="$(pwd)"
PAIR_DIR=".pair"
ALLOW_DIRTY=0
CLAUDE_MODE="interactive"
CLAUDE_TIMEOUT=1800
CLAUDE_PERMISSION_MODE="acceptEdits"
CODEX_MODEL=""
CLAUDE_MODEL=""
KEEP_TMUX=0
TASK=""

usage() {
  cat <<'EOF'
Usage:
  ./pair.sh [options] "task to implement"

Default flow:
  Claude plans and implements. Codex reviews the uncommitted diff.

Options:
  -i, --iterations N          Max Claude fix / Codex review loops. Default: 2
  -C, --repo DIR              Repo to work in. Default: current directory
  --allow-dirty               Allow starting with existing uncommitted changes
  --claude-mode MODE          interactive or print. Default: interactive
                               interactive uses Claude Code in tmux
                               print uses claude -p / Agent SDK credits
  --claude-timeout SEC        Seconds to wait for each Claude work turn. Default: 1800
  --claude-permission MODE    Claude permission mode. Default: acceptEdits
  --codex-model MODEL         Optional Codex reviewer model override
  --claude-model MODEL        Optional Claude builder model override, e.g. sonnet
  --keep-tmux                 Keep Claude tmux session open after the loop
  -h, --help                  Show this help

Example:
  ./pair.sh -i 3 "add rate limiting to the login endpoint"
EOF
}

die() {
  printf 'pair.sh: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '[pair] %s\n' "$*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

quote_cmd() {
  local quoted=()
  local arg

  for arg in "$@"; do
    printf -v arg '%q' "$arg"
    quoted+=("$arg")
  done

  local IFS=' '
  printf '%s' "${quoted[*]}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--iterations)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      MAX_ITERS="$2"
      shift 2
      ;;
    -C|--repo)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      REPO="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --claude-mode)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      CLAUDE_MODE="$2"
      shift 2
      ;;
    --claude-timeout)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      CLAUDE_TIMEOUT="$2"
      shift 2
      ;;
    --claude-permission)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      CLAUDE_PERMISSION_MODE="$2"
      shift 2
      ;;
    --codex-model)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      CODEX_MODEL="$2"
      shift 2
      ;;
    --claude-model)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      CLAUDE_MODEL="$2"
      shift 2
      ;;
    --keep-tmux)
      KEEP_TMUX=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      TASK="${*:-}"
      break
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      if [[ -z "$TASK" ]]; then
        TASK="$1"
      else
        TASK="$TASK $1"
      fi
      shift
      ;;
  esac
done

[[ -n "$TASK" ]] || {
  usage
  exit 1
}

[[ "$MAX_ITERS" =~ ^[0-9]+$ ]] || die "--iterations must be a positive integer"
[[ "$MAX_ITERS" -gt 0 ]] || die "--iterations must be greater than zero"
[[ "$CLAUDE_TIMEOUT" =~ ^[0-9]+$ ]] || die "--claude-timeout must be a positive integer"

case "$CLAUDE_MODE" in
  interactive|print) ;;
  *) die "--claude-mode must be interactive or print" ;;
esac

case "$CLAUDE_PERMISSION_MODE" in
  acceptEdits|auto|bypassPermissions|default|dontAsk|plan) ;;
  *) die "--claude-permission must be one of: acceptEdits, auto, bypassPermissions, default, dontAsk, plan" ;;
esac

REPO="$(cd "$REPO" && pwd)"
git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "$REPO is not inside a git repository"
REPO="$(git -C "$REPO" rev-parse --show-toplevel)"

require_cmd git
require_cmd codex
require_cmd claude
require_cmd jq
if [[ "$CLAUDE_MODE" == "interactive" ]]; then
  require_cmd tmux
fi

if [[ "$ALLOW_DIRTY" -eq 0 ]]; then
  if ! git -C "$REPO" diff --quiet -- . ':(exclude).pair/**'; then
    die "working tree has unstaged changes; commit/stash them or pass --allow-dirty"
  fi

  if ! git -C "$REPO" diff --cached --quiet -- . ':(exclude).pair/**'; then
    die "working tree has staged changes; commit/stash them or pass --allow-dirty"
  fi

  if [[ -n "$(git -C "$REPO" ls-files --others --exclude-standard -- . ':(exclude).pair/**')" ]]; then
    die "working tree has untracked files; commit/stash them or pass --allow-dirty"
  fi
fi

RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_REL="$PAIR_DIR/runs/$RUN_ID"
RUN_DIR="$REPO/$RUN_REL"
PROMPT_DIR="$RUN_DIR/prompts"
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$PROMPT_DIR" "$LOG_DIR"

SPEC_REL="$RUN_REL/SPEC.md"
SPEC_FILE="$REPO/$SPEC_REL"
CLAUDE_SESSION="pair_${RUN_ID}_claude"

CLAUDE_ALLOWED_TOOLS="Read,Grep,Glob,LS,Edit,MultiEdit,Write,Bash(git diff:*),Bash(git status:*),Bash(git show:*),Bash(git ls-files:*),Bash(npm run:*),Bash(npm test:*),Bash(npx:*),Bash(pnpm:*),Bash(yarn:*),Bash(cargo test:*),Bash(go test:*),Bash(pytest:*),Bash(python -m pytest:*),Bash(ruff:*),Bash(mypy:*),Bash(tsc:*)"
CLAUDE_DENIED_TOOLS="WebFetch,WebSearch,Bash(git commit:*),Bash(git push:*),Bash(git reset:*),Bash(git checkout:*),Bash(git clean:*),Bash(rm:*),Bash(curl:*),Bash(wget:*)"

write_claude_work_prompt() {
  local prompt_file="$1"
  local iteration="$2"
  local previous_review="${3:-}"
  local marker="PAIR_WORK_DONE_${iteration}:"

  if [[ -z "$previous_review" ]]; then
    cat > "$prompt_file" <<EOF
You are Claude Code acting as the implementation owner in a Claude + Codex review loop.

User task:
$TASK

Do the work in this order:
1. Inspect the repo enough to understand the existing patterns.
2. Write a short implementation spec at \`$SPEC_REL\`.
3. Implement the task against that spec.
4. Run the most relevant local checks you can discover.

Spec requirements:
- Intended behavior and acceptance criteria.
- Likely files/modules touched.
- Expected tests, lint, type checks, or manual checks.
- Non-goals and risky assumptions.
- Review checklist Codex should use for spec adherence, bugs/regressions, and missing best-practice additions.

Implementation rules:
- Keep changes scoped to the task.
- Prefer existing project patterns.
- Add or update tests when the risk justifies it.
- Do not commit, stage, push, or change branches.
- Do not edit files under \`$PAIR_DIR/\` except the spec and brief run notes.

Completion marker:
When the work turn is finished, print exactly one final line beginning with:
$marker

After that prefix, put compact one-line JSON:
{"status":"done","changed_files":["paths"],"checks_run":["commands or checks"],"notes":["short notes"]}

Do not wrap the marker JSON in Markdown.
This is Claude work iteration $iteration.
EOF
  else
    cat > "$prompt_file" <<EOF
You are Claude Code acting as the implementation owner in a Claude + Codex review loop.

User task:
$TASK

Spec:
\`$SPEC_REL\`

Codex reviewed the previous iteration and returned this JSON:
\`$previous_review\`

Fix the failed review items. Treat blockers, bugs, spec violations, unsafe behavior, and serious test gaps as required fixes. Treat best-practice suggestions as optional unless they reveal correctness, security, reliability, or maintainability risk.

Rules:
- Keep changes scoped to the spec and Codex review findings.
- Prefer existing project patterns.
- Add or update tests when the risk justifies it.
- Run the most relevant local checks you can discover.
- Do not commit, stage, push, or change branches.
- Do not edit files under \`$PAIR_DIR/\` except brief run notes.

Completion marker:
When the fix turn is finished, print exactly one final line beginning with:
$marker

After that prefix, put compact one-line JSON:
{"status":"done","changed_files":["paths"],"checks_run":["commands or checks"],"notes":["short notes"]}

Do not wrap the marker JSON in Markdown.
This is Claude fix iteration $iteration.
EOF
  fi
}

write_codex_review_prompt() {
  local prompt_file="$1"
  local iteration="$2"

  cat > "$prompt_file" <<EOF
You are Codex acting only as a reviewer/auditor for a Claude implementation.

Do not edit files. Do not write files. Do not commit, stage, push, or change branches.

Review this task:
$TASK

Review materials:
- Spec: \`$SPEC_REL\`
- Uncommitted git diff and untracked files from this repository.

Review goals:
1. Confirm the implementation satisfies the spec and user task.
2. Find bugs, regressions, broken edge cases, security risks, data-loss risks, and test gaps.
3. Identify best-practice additions that would materially improve correctness, maintainability, security, performance, or operability.

Verdict rules:
- Use "fail" for blockers, real bugs, spec violations, unsafe behavior, or important missing tests/checks.
- Use "pass" when the change is acceptable to ship.
- Best-practice suggestions are non-blocking unless they expose real risk.

Output rules:
- Print exactly one final line beginning with PAIR_REVIEW_JSON:
- After that prefix, put compact one-line JSON.
- Do not wrap the JSON in Markdown.
- Do not include any other text on the final line.

Required JSON shape:
{
  "verdict": "pass or fail",
  "blockers": ["required fixes only"],
  "bugs": ["bugs or likely regressions"],
  "tests_missing": ["important tests/checks that should be added or run"],
  "best_practice_suggestions": ["non-blocking improvements"],
  "risk_notes": ["remaining risks or assumptions"],
  "summary": "one sentence summary"
}

This is Codex review iteration $iteration.
EOF
}

extract_prefixed_json() {
  local capture_file="$1"
  local json_file="$2"
  local prefix="$3"
  local validation="$4"
  local line
  local json

  line="$(grep -a "$prefix" "$capture_file" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1

  json="${line#*"$prefix"}"
  json="${json//$'\r'/}"
  printf '%s\n' "$json" > "$json_file.tmp"

  if jq -e "$validation" "$json_file.tmp" >/dev/null 2>&1; then
    mv "$json_file.tmp" "$json_file"
    return 0
  fi

  rm -f "$json_file.tmp"
  return 1
}

start_claude_session() {
  local cmd

  cmd="$(quote_cmd \
    claude \
    --name "$CLAUDE_SESSION" \
    --permission-mode "$CLAUDE_PERMISSION_MODE" \
    --allowedTools "$CLAUDE_ALLOWED_TOOLS" \
    --disallowedTools "$CLAUDE_DENIED_TOOLS")"

  if [[ -n "$CLAUDE_MODEL" ]]; then
    cmd="$cmd $(quote_cmd --model "$CLAUDE_MODEL")"
  fi

  info "Starting Claude work session in tmux: $CLAUDE_SESSION"
  tmux new-session -d -s "$CLAUDE_SESSION" -c "$REPO" "$cmd"
  tmux set-option -t "$CLAUDE_SESSION" remain-on-exit on >/dev/null 2>&1 || true
  sleep 2
}

run_claude_interactive_work() {
  local prompt_file="$1"
  local capture_file="$2"
  local json_file="$3"
  local iteration="$4"
  local prefix="PAIR_WORK_DONE_${iteration}:"
  local deadline

  if ! tmux has-session -t "$CLAUDE_SESSION" >/dev/null 2>&1; then
    start_claude_session
  fi

  info "Sending work turn to Claude. You can watch with: tmux attach -t $CLAUDE_SESSION"
  tmux load-buffer -b "$CLAUDE_SESSION.prompt.$iteration" "$prompt_file"
  tmux paste-buffer -b "$CLAUDE_SESSION.prompt.$iteration" -t "$CLAUDE_SESSION"
  tmux send-keys -t "$CLAUDE_SESSION" Enter

  deadline=$((SECONDS + CLAUDE_TIMEOUT))
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    tmux capture-pane -pJ -S -4000 -t "$CLAUDE_SESSION" > "$capture_file" 2>/dev/null || true

    if extract_prefixed_json "$capture_file" "$json_file" "$prefix" 'type == "object" and .status == "done"'; then
      info "Claude work marker captured: ${json_file#$REPO/}"
      return 0
    fi

    sleep 5
  done

  tmux capture-pane -pJ -S -4000 -t "$CLAUDE_SESSION" > "$capture_file" 2>/dev/null || true
  die "Claude work timed out after ${CLAUDE_TIMEOUT}s. Session kept open: tmux attach -t $CLAUDE_SESSION"
}

run_claude_print_work() {
  local prompt_file="$1"
  local capture_file="$2"
  local json_file="$3"
  local iteration="$4"
  local raw_file="${json_file%.json}.raw.json"
  local log_file="${json_file%.json}.stderr.log"
  local prompt_text
  local prefix="PAIR_WORK_DONE_${iteration}:"
  local cmd=(claude -p --output-format json \
    --permission-mode "$CLAUDE_PERMISSION_MODE" \
    --allowedTools "$CLAUDE_ALLOWED_TOOLS" \
    --disallowedTools "$CLAUDE_DENIED_TOOLS")

  if [[ -n "$CLAUDE_MODEL" ]]; then
    cmd+=(--model "$CLAUDE_MODEL")
  fi

  prompt_text="$(< "$prompt_file")"

  info "Running Claude work turn with claude -p; this uses Agent SDK credits"
  if ! "${cmd[@]}" "$prompt_text" > "$raw_file" 2> "$log_file"; then
    die "Claude print work failed. See $log_file"
  fi

  jq -r '.result // empty' "$raw_file" > "$capture_file"

  if ! extract_prefixed_json "$capture_file" "$json_file" "$prefix" 'type == "object" and .status == "done"'; then
    die "Claude print work did not return a valid completion marker. See $raw_file"
  fi
}

run_claude_work() {
  local iteration="$1"
  local previous_review="${2:-}"
  local prompt_file="$PROMPT_DIR/claude-work-$iteration.md"
  local capture_file="$RUN_DIR/claude-work-$iteration.capture.txt"
  local json_file="$RUN_DIR/claude-work-$iteration.json"

  write_claude_work_prompt "$prompt_file" "$iteration" "$previous_review"

  if [[ "$CLAUDE_MODE" == "interactive" ]]; then
    run_claude_interactive_work "$prompt_file" "$capture_file" "$json_file" "$iteration"
  else
    run_claude_print_work "$prompt_file" "$capture_file" "$json_file" "$iteration"
  fi
}

run_codex_review() {
  local iteration="$1"
  local prompt_file="$PROMPT_DIR/codex-review-$iteration.md"
  local capture_file="$RUN_DIR/codex-review-$iteration.final.txt"
  local stdout_file="$RUN_DIR/codex-review-$iteration.stdout.txt"
  local log_file="$LOG_DIR/codex-review-$iteration.stderr.log"
  local json_file="$RUN_DIR/codex-review-$iteration.json"
  local cmd=(codex --ask-for-approval never --sandbox read-only --cd "$REPO")

  if [[ -n "$CODEX_MODEL" ]]; then
    cmd+=(--model "$CODEX_MODEL")
  fi

  cmd+=(exec review --uncommitted --ephemeral -o "$capture_file" -)

  write_codex_review_prompt "$prompt_file" "$iteration"

  info "Running Codex review iteration $iteration"
  if ! "${cmd[@]}" < "$prompt_file" > "$stdout_file" 2> "$log_file"; then
    die "Codex review failed. See $log_file"
  fi

  if ! extract_prefixed_json "$capture_file" "$json_file" "PAIR_REVIEW_JSON:" 'type == "object" and (.verdict == "pass" or .verdict == "fail")'; then
    die "Codex review did not return valid PAIR_REVIEW_JSON. See $capture_file"
  fi

  REVIEW_JSON="$json_file"
}

finish_claude_session() {
  if [[ "$CLAUDE_MODE" == "interactive" && "$KEEP_TMUX" -eq 0 ]]; then
    tmux kill-session -t "$CLAUDE_SESSION" >/dev/null 2>&1 || true
  elif [[ "$CLAUDE_MODE" == "interactive" ]]; then
    info "Kept Claude session open: tmux attach -t $CLAUDE_SESSION"
  fi
}

info "Repo: $REPO"
info "Run artifacts: $RUN_REL"
info "Flow: Claude builds, Codex reviews"
info "Claude mode: $CLAUDE_MODE"

previous_review=""
final_verdict="fail"
REVIEW_JSON=""

for iteration in $(seq 1 "$MAX_ITERS"); do
  run_claude_work "$iteration" "$previous_review"

  if [[ ! -s "$SPEC_FILE" ]]; then
    die "Claude did not create $SPEC_REL. Check $RUN_DIR/claude-work-$iteration.capture.txt"
  fi

  run_codex_review "$iteration"
  final_verdict="$(jq -r '.verdict' "$REVIEW_JSON")"

  info "Codex verdict for iteration $iteration: $final_verdict"

  if [[ "$final_verdict" == "pass" ]]; then
    info "Pair loop passed."
    info "Review JSON: ${REVIEW_JSON#$REPO/}"
    info "Current git status:"
    git -C "$REPO" status --short -- . ':(exclude).pair/**'
    finish_claude_session
    exit 0
  fi

  previous_review="${REVIEW_JSON#$REPO/}"
  info "Review failed; Claude will fix findings on the next iteration."
done

info "Reached max iterations without Codex sign-off."
info "Last review JSON: ${REVIEW_JSON#$REPO/}"
git -C "$REPO" status --short -- . ':(exclude).pair/**'
finish_claude_session
exit 2

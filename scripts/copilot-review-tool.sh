#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

AUTHOR_LOGIN="copilot-pull-request-reviewer"

usage() {
    cat <<'EOF'
Usage:
  scripts/copilot-review-tool.sh threads --repo OWNER/REPO --pr NUMBER [--state unresolved|resolved|all] [--format json|markdown] [--output FILE]
  scripts/copilot-review-tool.sh lessons --repo OWNER/REPO --pr NUMBER [--state unresolved|resolved|all] [--output FILE]
  scripts/copilot-review-tool.sh scan --repo OWNER/REPO [--repo OWNER/REPO ...] [--state unresolved|resolved|all] [--output-dir DIR]
  scripts/copilot-review-tool.sh resolve --thread-id ID [--thread-id ID ...]
EOF
}

need() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required command: $1" >&2
        exit 1
    }
}

write_output() {
    local content="$1"
    local output_file="${2:-}"

    if [[ -n "$output_file" ]]; then
        mkdir -p "$(dirname "$output_file")"
        printf '%s\n' "$content" >"$output_file"
        echo "Wrote output to $output_file"
        return
    fi

    printf '%s\n' "$content"
}

split_repo() {
    [[ "$1" == */* ]] || {
        echo "Repository must be in OWNER/REPO format: $1" >&2
        exit 1
    }

    REPO_OWNER="${1%%/*}"
    REPO_NAME="${1#*/}"
}

repo_slug() {
    printf '%s' "$1" | tr '/' '-'
}

first_sentence() {
    printf '%s' "$1" | awk '{gsub(/[[:space:]]+/," "); text=text $0} END {sub(/^ /,"",text); match(text, /[.!?]/); print RSTART ? substr(text, 1, RSTART) : text}'
}

normalize_body() {
    printf '%s' "$1" | perl -0pe 's/```suggestion.*?```//sg; s/```.*?```//sg; s/\s+/ /g; s/^\s+//; s/\s+$//;'
}

classify_finding() {
    local lowered

    lowered="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    case "$lowered" in
        *changelog*) echo "Promote to changelog structure guardrails (template, lint, or review script)." ;;
        *checklist*|*self-contained*) echo "Promote to repo-local Copilot instructions or instruction validation rules." ;;
        *applyto*|*workflow*) echo "Promote to workflow instruction validation or reusable workflow guardrails." ;;
        *"line length"*|*markdown*|*heading*) echo "Promote to markdownlint/prettier configuration or content templates." ;;
        *) echo "Promote to instructions first; if it repeats, turn it into a hook, lint rule, or test." ;;
    esac
}

fetch_threads_json() {
    local repo="$1"
    local pr_number="$2"
    local query

    split_repo "$repo"
    query=$(cat <<'EOF'
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100) {
        nodes {
          id
          isResolved
          path
          line
          comments(first:20) {
            nodes {
              author { login }
              body
              url
            }
          }
        }
      }
    }
  }
}
EOF
)

    PAGER=cat GH_PAGER=cat gh api graphql \
        -F owner="$REPO_OWNER" \
        -F name="$REPO_NAME" \
        -F number="$pr_number" \
        -f query="$query"
}

list_open_prs_json() {
    PAGER=cat GH_PAGER=cat gh pr list --repo "$1" --state open --limit 100 --json number,title,url,isDraft
}

filter_threads() {
    jq --arg state "$1" --arg author "$AUTHOR_LOGIN" '
        .data.repository.pullRequest.reviewThreads.nodes
        | map({
            id,
            isResolved,
            path,
            line,
            comments: (.comments.nodes | map(select(.author.login == $author)))
          })
        | map(select(.comments | length > 0))
        | map(select(
            ($state == "all")
            or ($state == "unresolved" and (.isResolved == false))
            or ($state == "resolved" and (.isResolved == true))
          ))'
}

render_threads_markdown() {
    local repo="$1"
    local pr_number="$2"
    local state="$3"
    local threads_json="$4"
    local output count generated_at

    generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    count="$(printf '%s' "$threads_json" | jq 'length')"
    output="# Copilot Review Threads

- Repository: $repo
- Pull Request: #$pr_number
- State: $state
- Generated: $generated_at
- Matching threads: $count"

    if [[ "$count" == "0" ]]; then
        printf '%s\n\nNo matching Copilot review threads found.\n' "$output"
        return
    fi

    while IFS= read -r thread; do
        local body sentence

        body="$(printf '%s' "$thread" | jq -r '.comments[0].body')"
        sentence="$(first_sentence "$(normalize_body "$body")")"
        output+=$'\n\n'
        output+="## $(printf '%s' "$thread" | jq -r '.path'):$(printf '%s' "$thread" | jq -r '.line // "-"')"
        output+=$'\n'
        output+="- Thread ID: $(printf '%s' "$thread" | jq -r '.id')"
        output+=$'\n'
        output+="- Status: $(printf '%s' "$thread" | jq -r 'if .isResolved then "resolved" else "unresolved" end')"
        output+=$'\n'
        output+="- URL: $(printf '%s' "$thread" | jq -r '.comments[0].url')"
        output+=$'\n'
        output+="- Summary: $sentence"
    done < <(printf '%s' "$threads_json" | jq -c '.[]')

    printf '%s\n' "$output"
}

render_lessons_markdown() {
    local repo="$1"
    local pr_number="$2"
    local state="$3"
    local threads_json="$4"
    local output count generated_at index

    generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    count="$(printf '%s' "$threads_json" | jq 'length')"
    output="# Copilot Review Lessons

- Repository: $repo
- Pull Request: #$pr_number
- State: $state
- Generated: $generated_at
- Source threads: $count

## How To Use

- Persist repeated findings in repo-owned files, not only in chat history.
- Prefer this escalation order: instructions -> hook/lint -> test/CI.
- Resolve review threads only after the fix is pushed and verified."

    if [[ "$count" == "0" ]]; then
        printf '%s\n\nNo matching Copilot review threads found.\n' "$output"
        return
    fi

    index=0
    while IFS= read -r thread; do
        local body normalized summary promotion

        index=$((index + 1))
        body="$(printf '%s' "$thread" | jq -r '.comments[0].body')"
        normalized="$(normalize_body "$body")"
        summary="$(first_sentence "$normalized")"
        promotion="$(classify_finding "$normalized")"
        output+=$'\n\n'
        output+="## Lesson $index"
        output+=$'\n'
        output+="- Source: $(printf '%s' "$thread" | jq -r '.path'):$(printf '%s' "$thread" | jq -r '.line // "-"')"
        output+=$'\n'
        output+="- Review URL: $(printf '%s' "$thread" | jq -r '.comments[0].url')"
        output+=$'\n'
        output+="- Finding: $summary"
        output+=$'\n'
        output+="- Durable action: $promotion"
    done < <(printf '%s' "$threads_json" | jq -c '.[]')

    printf '%s\n' "$output"
}

scan_repo() {
    local repo="$1"
    local state="$2"
    local output_dir="$3"
    local pr_list repo_dir total found summary

    pr_list="$(list_open_prs_json "$repo")"
    repo_dir="$output_dir/$(repo_slug "$repo")"
    total="$(printf '%s' "$pr_list" | jq 'map(select(.isDraft == false)) | length')"
    found=0
    mkdir -p "$repo_dir"
    summary="## $repo
- Open non-draft PRs: $total"

    while IFS= read -r pr; do
        local pr_number pr_title pr_url threads_json count prefix

        pr_number="$(printf '%s' "$pr" | jq -r '.number')"
        pr_title="$(printf '%s' "$pr" | jq -r '.title')"
        pr_url="$(printf '%s' "$pr" | jq -r '.url')"
        threads_json="$(fetch_threads_json "$repo" "$pr_number" | filter_threads "$state")"
        count="$(printf '%s' "$threads_json" | jq 'length')"

        [[ "$count" == "0" ]] && continue

        found=$((found + 1))
        prefix="$repo_dir/pr-$pr_number"
        render_threads_markdown "$repo" "$pr_number" "$state" "$threads_json" >"$prefix-threads.md"
        render_lessons_markdown "$repo" "$pr_number" "$state" "$threads_json" >"$prefix-lessons.md"
        summary+=$'\n'
        summary+="- PR #$pr_number: $pr_title"
        summary+=$'\n'
        summary+="  URL: $pr_url"
        summary+=$'\n'
        summary+="  Matching threads: $count"
        summary+=$'\n'
        summary+="  Threads artifact: $(repo_slug "$repo")/pr-$pr_number-threads.md"
        summary+=$'\n'
        summary+="  Lessons artifact: $(repo_slug "$repo")/pr-$pr_number-lessons.md"
    done < <(printf '%s' "$pr_list" | jq -c '.[] | select(.isDraft == false)')

    if [[ "$found" == "0" ]]; then
        summary+=$'\n- Matching PRs with Copilot findings: 0'
    fi

    printf '%s\n' "$summary"
}

resolve_thread() {
    local query

    query=$(cat <<'EOF'
mutation($threadId:ID!) {
  resolveReviewThread(input:{threadId:$threadId}) {
    thread { id isResolved }
  }
}
EOF
)

    PAGER=cat GH_PAGER=cat gh api graphql -f query="$query" -F threadId="$1" >/dev/null
    echo "Resolved review thread: $1"
}

command_threads() {
    local repo="" pr_number="" state="unresolved" format="markdown" output_file="" threads_json rendered

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) repo="$2"; shift 2 ;;
            --pr) pr_number="$2"; shift 2 ;;
            --state) state="$2"; shift 2 ;;
            --format) format="$2"; shift 2 ;;
            --output) output_file="$2"; shift 2 ;;
            *) echo "Unknown option for threads: $1" >&2; usage; exit 1 ;;
        esac
    done

    [[ -n "$repo" && -n "$pr_number" ]] || { echo "threads requires --repo and --pr" >&2; usage; exit 1; }
    threads_json="$(fetch_threads_json "$repo" "$pr_number" | filter_threads "$state")"
    if [[ "$format" == "json" ]]; then rendered="$(printf '%s' "$threads_json" | jq '.')"; else rendered="$(render_threads_markdown "$repo" "$pr_number" "$state" "$threads_json")"; fi
    write_output "$rendered" "$output_file"
}

command_lessons() {
    local repo="" pr_number="" state="all" output_file="" threads_json

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) repo="$2"; shift 2 ;;
            --pr) pr_number="$2"; shift 2 ;;
            --state) state="$2"; shift 2 ;;
            --output) output_file="$2"; shift 2 ;;
            *) echo "Unknown option for lessons: $1" >&2; usage; exit 1 ;;
        esac
    done

    [[ -n "$repo" && -n "$pr_number" ]] || { echo "lessons requires --repo and --pr" >&2; usage; exit 1; }
    threads_json="$(fetch_threads_json "$repo" "$pr_number" | filter_threads "$state")"
    write_output "$(render_lessons_markdown "$repo" "$pr_number" "$state" "$threads_json")" "$output_file"
}

command_scan() {
    local repos=() state="unresolved" output_dir="copilot-review-memory" summary

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) repos+=("$2"); shift 2 ;;
            --state) state="$2"; shift 2 ;;
            --output-dir) output_dir="$2"; shift 2 ;;
            *) echo "Unknown option for scan: $1" >&2; usage; exit 1 ;;
        esac
    done

    [[ ${#repos[@]} -gt 0 ]] || { echo "scan requires at least one --repo" >&2; usage; exit 1; }
    mkdir -p "$output_dir"
    summary="# Copilot Review Scan Summary

- Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- State: $state
- Repositories scanned: ${#repos[@]}"

    for repo in "${repos[@]}"; do
        summary+=$'\n\n'
        summary+="$(scan_repo "$repo" "$state" "$output_dir")"
    done

    printf '%s\n' "$summary" >"$output_dir/summary.md"
    cat "$output_dir/summary.md"
}

command_resolve() {
    local thread_ids=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --thread-id) thread_ids+=("$2"); shift 2 ;;
            *) echo "Unknown option for resolve: $1" >&2; usage; exit 1 ;;
        esac
    done

    [[ ${#thread_ids[@]} -gt 0 ]] || { echo "resolve requires at least one --thread-id" >&2; usage; exit 1; }
    for thread_id in "${thread_ids[@]}"; do resolve_thread "$thread_id"; done
}

main() {
    local subcommand="${1:-}"

    need gh
    need jq
    need perl
    [[ -n "$subcommand" ]] || { usage; exit 1; }
    shift || true

    case "$subcommand" in
        threads) command_threads "$@" ;;
        lessons) command_lessons "$@" ;;
        scan) command_scan "$@" ;;
        resolve) command_resolve "$@" ;;
        --help|-h|help) usage ;;
        *) echo "Unknown subcommand: $subcommand" >&2; usage; exit 1 ;;
    esac
}

main "$@"

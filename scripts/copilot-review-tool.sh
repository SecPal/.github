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
  scripts/copilot-review-tool.sh resolve --thread-id ID [--thread-id ID ...]

Examples:
  scripts/copilot-review-tool.sh threads --repo SecPal/api --pr 557 --state unresolved --format markdown
  scripts/copilot-review-tool.sh lessons --repo SecPal/frontend --pr 486 --output docs/copilot-review-memory/frontend-pr-486.md
  scripts/copilot-review-tool.sh resolve --thread-id PRRT_xxx --thread-id PRRT_yyy

Notes:
  - This tool automates the durable parts of the Copilot review workflow.
  - It cannot write to the agent's private runtime memory store; instead it emits repo-owned artifacts.
  - Use the generated lessons output to promote recurring findings into instructions, hooks, lint rules, or tests.
EOF
}

require_command() {
    local command_name="$1"

    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Missing required command: $command_name" >&2
        exit 1
    fi
}

ensure_output_dir() {
    local output_file="$1"

    if [[ -n "$output_file" ]]; then
        mkdir -p "$(dirname "$output_file")"
    fi
}

write_output() {
    local content="$1"
    local output_file="$2"

    if [[ -n "$output_file" ]]; then
        ensure_output_dir "$output_file"
        printf '%s\n' "$content" > "$output_file"
        echo "Wrote output to $output_file"
    else
        printf '%s\n' "$content"
    fi
}

split_repo() {
    local repo="$1"

    if [[ "$repo" != */* ]]; then
        echo "Repository must be in OWNER/REPO format: $repo" >&2
        exit 1
    fi

    REPO_OWNER="${repo%%/*}"
    REPO_NAME="${repo#*/}"
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
                            id
                            author { login }
                            body
                            url
                            createdAt
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

filter_threads() {
    local state="$1"

    jq \
        --arg state "$state" \
        --arg author "$AUTHOR_LOGIN" '
        .data.repository.pullRequest.reviewThreads.nodes
        | map(
            . as $thread
            | {
                id: $thread.id,
                isResolved: $thread.isResolved,
                path: $thread.path,
                line: $thread.line,
                comments: (
                    $thread.comments.nodes
                    | map(select(.author.login == $author))
                )
            }
        )
        | map(select(.comments | length > 0))
        | map(
            select(
                ($state == "all")
                or ($state == "unresolved" and (.isResolved == false))
                or ($state == "resolved" and (.isResolved == true))
            )
        )'
}

first_sentence() {
    local text="$1"

    printf '%s' "$text" | awk '
        {
            gsub(/[[:space:]]+/, " ");
            text = text $0;
        }
        END {
            sub(/^ /, "", text);
            match(text, /[.!?]/);
            if (RSTART > 0) {
                print substr(text, 1, RSTART);
            } else {
                print text;
            }
        }
    '
}

normalize_body() {
    local text="$1"

    printf '%s' "$text" | perl -0pe 's/```suggestion.*?```//sg; s/```.*?```//sg; s/\s+/ /g; s/^\s+//; s/\s+$//;'
}

classify_finding() {
    local body="$1"
    local lowered

    lowered="$(printf '%s' "$body" | tr '[:upper:]' '[:lower:]')"

    if [[ "$lowered" == *"changelog"* ]]; then
        echo "Promote to changelog structure guardrails (template, lint, or review script)."
        return
    fi

    if [[ "$lowered" == *"checklist"* ]] || [[ "$lowered" == *"self-contained"* ]]; then
        echo "Promote to repo-local Copilot instructions or instruction validation rules."
        return
    fi

    if [[ "$lowered" == *"applyto"* ]] || [[ "$lowered" == *"workflow"* ]]; then
        echo "Promote to workflow instruction validation or reusable workflow guardrails."
        return
    fi

    if [[ "$lowered" == *"line length"* ]] || [[ "$lowered" == *"markdown"* ]] || [[ "$lowered" == *"heading"* ]]; then
        echo "Promote to markdownlint/prettier configuration or content templates."
        return
    fi

    echo "Promote to instructions first; if it repeats, turn it into a hook, lint rule, or test."
}

render_threads_markdown() {
    local repo="$1"
    local pr_number="$2"
    local state="$3"
    local threads_json="$4"
    local generated_at
    local count
    local output

    generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    count="$(printf '%s' "$threads_json" | jq 'length')"

    output=$(cat <<EOF
# Copilot Review Threads

- Repository: $repo
- Pull Request: #$pr_number
- State: $state
- Generated: $generated_at
- Matching threads: $count
EOF
)

    if [[ "$count" == "0" ]]; then
        output+=$'\n\nNo matching Copilot review threads found.'
        printf '%s\n' "$output"
        return
    fi

    while IFS= read -r thread; do
        local thread_id path line status body url sentence

        thread_id="$(printf '%s' "$thread" | jq -r '.id')"
        path="$(printf '%s' "$thread" | jq -r '.path')"
        line="$(printf '%s' "$thread" | jq -r '.line // "-"')"
        status="$(printf '%s' "$thread" | jq -r 'if .isResolved then "resolved" else "unresolved" end')"
        body="$(printf '%s' "$thread" | jq -r '.comments[0].body')"
        url="$(printf '%s' "$thread" | jq -r '.comments[0].url')"
        sentence="$(first_sentence "$(normalize_body "$body")")"

        output+=$'\n\n'
        output+="## $path:$line"
        output+=$'\n'
        output+="- Thread ID: $thread_id"
        output+=$'\n'
        output+="- Status: $status"
        output+=$'\n'
        output+="- URL: $url"
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
    local generated_at
    local count
    local output

    generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    count="$(printf '%s' "$threads_json" | jq 'length')"

    output=$(cat <<EOF
# Copilot Review Lessons

- Repository: $repo
- Pull Request: #$pr_number
- State: $state
- Generated: $generated_at
- Source threads: $count

## How To Use

- Persist repeated findings in repo-owned files, not only in chat history.
- Prefer this escalation order: instructions -> hook/lint -> test/CI.
- Resolve review threads only after the fix is pushed and verified.
EOF
)

    if [[ "$count" == "0" ]]; then
        output+=$'\n\nNo matching Copilot review threads found.'
        printf '%s\n' "$output"
        return
    fi

    local index=0
    while IFS= read -r thread; do
        local path line body url normalized summary promotion

        index=$((index + 1))
        path="$(printf '%s' "$thread" | jq -r '.path')"
        line="$(printf '%s' "$thread" | jq -r '.line // "-"')"
        body="$(printf '%s' "$thread" | jq -r '.comments[0].body')"
        url="$(printf '%s' "$thread" | jq -r '.comments[0].url')"
        normalized="$(normalize_body "$body")"
        summary="$(first_sentence "$normalized")"
        promotion="$(classify_finding "$normalized")"

        output+=$'\n\n'
        output+="## Lesson $index"
        output+=$'\n'
        output+="- Source: $path:$line"
        output+=$'\n'
        output+="- Review URL: $url"
        output+=$'\n'
        output+="- Finding: $summary"
        output+=$'\n'
        output+="- Durable action: $promotion"
    done < <(printf '%s' "$threads_json" | jq -c '.[]')

    printf '%s\n' "$output"
}

resolve_thread() {
    local thread_id="$1"
        local query

        query=$(cat <<'EOF'
mutation($threadId:ID!) {
    resolveReviewThread(input:{threadId:$threadId}) {
        thread {
            id
            isResolved
        }
    }
}
EOF
)

    PAGER=cat GH_PAGER=cat gh api graphql \
                -f query="$query" \
        -F threadId="$thread_id" >/dev/null

    echo "Resolved review thread: $thread_id"
}

command_threads() {
    local repo=""
    local pr_number=""
    local state="unresolved"
    local format="markdown"
    local output_file=""
    local threads_json
    local rendered

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo)
                repo="$2"
                shift 2
                ;;
            --pr)
                pr_number="$2"
                shift 2
                ;;
            --state)
                state="$2"
                shift 2
                ;;
            --format)
                format="$2"
                shift 2
                ;;
            --output)
                output_file="$2"
                shift 2
                ;;
            *)
                echo "Unknown option for threads: $1" >&2
                usage
                exit 1
                ;;
        esac
    done

    if [[ -z "$repo" || -z "$pr_number" ]]; then
        echo "threads requires --repo and --pr" >&2
        usage
        exit 1
    fi

    threads_json="$(fetch_threads_json "$repo" "$pr_number" | filter_threads "$state")"

    if [[ "$format" == "json" ]]; then
        rendered="$(printf '%s' "$threads_json" | jq '.')"
    else
        rendered="$(render_threads_markdown "$repo" "$pr_number" "$state" "$threads_json")"
    fi

    write_output "$rendered" "$output_file"
}

command_lessons() {
    local repo=""
    local pr_number=""
    local state="all"
    local output_file=""
    local threads_json
    local rendered

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo)
                repo="$2"
                shift 2
                ;;
            --pr)
                pr_number="$2"
                shift 2
                ;;
            --state)
                state="$2"
                shift 2
                ;;
            --output)
                output_file="$2"
                shift 2
                ;;
            *)
                echo "Unknown option for lessons: $1" >&2
                usage
                exit 1
                ;;
        esac
    done

    if [[ -z "$repo" || -z "$pr_number" ]]; then
        echo "lessons requires --repo and --pr" >&2
        usage
        exit 1
    fi

    threads_json="$(fetch_threads_json "$repo" "$pr_number" | filter_threads "$state")"
    rendered="$(render_lessons_markdown "$repo" "$pr_number" "$state" "$threads_json")"

    write_output "$rendered" "$output_file"
}

command_resolve() {
    local thread_ids=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --thread-id)
                thread_ids+=("$2")
                shift 2
                ;;
            *)
                echo "Unknown option for resolve: $1" >&2
                usage
                exit 1
                ;;
        esac
    done

    if [[ ${#thread_ids[@]} -eq 0 ]]; then
        echo "resolve requires at least one --thread-id" >&2
        usage
        exit 1
    fi

    for thread_id in "${thread_ids[@]}"; do
        resolve_thread "$thread_id"
    done
}

main() {
    require_command gh
    require_command jq
    require_command perl

    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi

    local subcommand="$1"
    shift

    case "$subcommand" in
        threads)
            command_threads "$@"
            ;;
        lessons)
            command_lessons "$@"
            ;;
        resolve)
            command_resolve "$@"
            ;;
        --help|-h|help)
            usage
            ;;
        *)
            echo "Unknown subcommand: $subcommand" >&2
            usage
            exit 1
            ;;
    esac
}

main "$@"

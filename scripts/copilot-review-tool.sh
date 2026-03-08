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
    scripts/copilot-review-tool.sh scan --repo OWNER/REPO [--repo OWNER/REPO ...] [--state unresolved|resolved|all] [--max-prs NUMBER] [--output-dir DIR]
    scripts/copilot-review-tool.sh track --repo OWNER/REPO --input-dir DIR [--threshold NUMBER] [--label LABEL ...] [--run-url URL] [--output FILE] [--dry-run]
  scripts/copilot-review-tool.sh resolve --thread-id ID [--thread-id ID ...]
EOF
}

need() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required command: $1" >&2
        exit 1
    }
}

require_value() {
    local option_name="$1"
    local option_value="${2:-}"

    if [[ -z "$option_value" || "$option_value" == --* ]]; then
        echo "Option $option_name requires a value" >&2
        exit 1
    fi
}

validate_state() {
    case "$1" in
        unresolved|resolved|all) ;;
        *)
            echo "Invalid --state value: $1" >&2
            exit 1
            ;;
    esac
}

validate_format() {
    case "$1" in
        json|markdown) ;;
        *)
            echo "Invalid --format value: $1" >&2
            exit 1
            ;;
    esac
}

validate_positive_integer() {
    local option_name="$1"
    local value="$2"

    [[ "$value" =~ ^[1-9][0-9]*$ ]] || {
        echo "Invalid ${option_name} value: ${value} (must be a positive integer)" >&2
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

trim_text() {
    printf '%s' "$1" | perl -pe 's/\s+/ /g; s/^\s+//; s/\s+$//;'
}

normalize_body() {
    printf '%s' "$1" | perl -0pe 's/```suggestion.*?```//sg; s/```.*?```//sg; s/\s+/ /g; s/^\s+//; s/\s+$//;'
}

slugify() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | perl -pe 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//;'
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

finding_category_title() {
    local lowered summary

    lowered="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    summary="$(trim_text "$(first_sentence "$1")")"

    case "$lowered" in
        *command\ substitution*|*arbitrary\ command\ execution*|*shell-safe*|*untrusted\ filename*|*malicious_command*|*execute\ by\ the\ shell*)
            echo "Shell-safe handling of untrusted input"
            ;;
        *package-lock*|*lockfile*|*package\ metadata*)
            echo "Package metadata and lockfile consistency"
            ;;
        *pagination*|*rate\ limit*|*one\ graphql\ request\ per\ pr*|*max-prs*)
            echo "GitHub API pagination and scan bounds"
            ;;
        *artifact\ noise*|*artifact\ upload*|*hourly\ artifact*|*schedule*|*empty\ artifacts*)
            echo "Workflow artifact noise and scheduling"
            ;;
        *frontmatter*)
            echo "Instruction frontmatter validation"
            ;;
        *detect_repo_type*|*contracts\ detection*|*documented\ detection\ logic*|*openapi*|*fall\ through\ to\ be\ detected\ as\ org*)
            echo "Repository detection and docs alignment"
            ;;
        *changelog*)
            echo "Changelog terminology and structure"
            ;;
        *requires\ a\ value*|*invalid\ --state*|*invalid\ --format*|*cli\ parser*|*flag*)
            echo "CLI argument validation"
            ;;
        *runtime\ model*|*self-contained*|*repo-local\ instruction*)
            echo "Copilot instruction runtime model consistency"
            ;;
        *)
            if [[ -z "$summary" ]]; then
                echo "General review pattern"
            else
                echo "General review pattern: ${summary:0:72}"
            fi
            ;;
    esac
}

render_findings_jsonl() {
    local repo="$1"
    local pr_number="$2"
    local pr_url="$3"
    local state="$4"
    local threads_json="$5"
    local generated_at

    generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    while IFS= read -r thread; do
        local body normalized summary category_title category_key promotion

        body="$(printf '%s' "$thread" | jq -r '.comments[0].body')"
        normalized="$(normalize_body "$body")"
        summary="$(trim_text "$(first_sentence "$normalized")")"
        category_title="$(finding_category_title "$normalized")"
        category_key="$(slugify "$category_title")"
        promotion="$(classify_finding "$normalized")"

        jq -nc \
            --arg repo "$repo" \
            --argjson pr_number "$pr_number" \
            --arg pr_url "$pr_url" \
            --arg source_key "$repo#$pr_number" \
            --arg state "$state" \
            --arg seen_at "$generated_at" \
            --arg path "$(printf '%s' "$thread" | jq -r '.path')" \
            --argjson line "$(printf '%s' "$thread" | jq '.line // null')" \
            --arg review_url "$(printf '%s' "$thread" | jq -r '.comments[0].url')" \
            --arg summary "$summary" \
            --arg category_key "$category_key" \
            --arg category_title "$category_title" \
            --arg promotion "$promotion" \
            '{
                repo: $repo,
                pr_number: $pr_number,
                pr_url: $pr_url,
                source_key: $source_key,
                state: $state,
                seen_at: $seen_at,
                path: $path,
                line: $line,
                review_url: $review_url,
                summary: $summary,
                category_key: $category_key,
                category_title: $category_title,
                promotion: $promotion
            }'
    done < <(printf '%s' "$threads_json" | jq -c '.[]')
}

load_findings_json() {
    local input_dir="$1"
    local files=()
    local file

    while IFS= read -r -d '' file; do
        files+=("$file")
    done < <(find "$input_dir" -type f -name 'pr-*-findings.jsonl' -print0 2>/dev/null)

    if [[ ${#files[@]} -eq 0 ]]; then
        printf '[]\n'
        return
    fi

    jq -s '.' "${files[@]}"
}

extract_tracker_state() {
    local extracted

    extracted="$(perl -0ne 'if (/<!-- copilot-review-tracker-state:\s*(\{.*\})\s*-->/s) { print $1 } else { print "{}" }' <<<"$1")"
    if printf '%s' "$extracted" | jq -e . >/dev/null 2>&1; then
        printf '%s\n' "$extracted"
        return
    fi

    printf '{}\n'
}

build_tracker_state() {
    local grouped_findings="$1"
    local threshold="$2"
    local run_url="$3"

    printf '%s' "$grouped_findings" | jq \
        --argjson threshold "$threshold" \
        --arg run_url "$run_url" \
        '{
            key: .[0].category_key,
            category: .[0].category_title,
            promotion: .[0].promotion,
            threshold: $threshold,
            sightings: map(. + { run_url: $run_url })
        }'
}

merge_tracker_state() {
    local existing_state="$1"
    local new_state="$2"

    jq -s '
        (.[0] // {}) as $old |
        (.[1] // {}) as $new |
        {
            key: ($new.key // $old.key),
            category: ($new.category // $old.category),
            promotion: ($new.promotion // $old.promotion),
            threshold: ($new.threshold // $old.threshold // 2),
            sightings: ((($old.sightings // []) + ($new.sightings // []))
                | unique_by((.review_url // "") + "|" + (.source_key // "") + "|" + (.summary // ""))
                | sort_by(.seen_at, .source_key, .review_url))
        }' <<<"$existing_state
$new_state"
}

render_tracker_issue_body() {
    local state_json="$1"
    local compact key category threshold distinct_prs total_findings first_seen last_seen promotion output

    compact="$(printf '%s' "$state_json" | jq -c '.')"
    key="$(printf '%s' "$state_json" | jq -r '.key')"
    category="$(printf '%s' "$state_json" | jq -r '.category')"
    threshold="$(printf '%s' "$state_json" | jq -r '.threshold')"
    distinct_prs="$(printf '%s' "$state_json" | jq '[.sightings[].source_key] | unique | length')"
    total_findings="$(printf '%s' "$state_json" | jq '.sightings | length')"
    first_seen="$(printf '%s' "$state_json" | jq -r '[.sightings[].seen_at] | min // "-"')"
    last_seen="$(printf '%s' "$state_json" | jq -r '[.sightings[].seen_at] | max // "-"')"
    promotion="$(printf '%s' "$state_json" | jq -r '.promotion')"
    output="<!-- copilot-review-tracker-state: $compact -->

# Copilot Learning: $category

## Summary

- Category key: $key
- Distinct pull requests: $distinct_prs
- Total findings: $total_findings
- Threshold: $threshold
- First seen: $first_seen
- Last seen: $last_seen
- Durable action: $promotion

## Source Pull Requests"

    while IFS= read -r source; do
        local source_key pr_url run_url seen_at

        source_key="$(printf '%s' "$source" | jq -r '.source_key')"
        pr_url="$(printf '%s' "$source" | jq -r '.pr_url')"
        run_url="$(printf '%s' "$source" | jq -r '.run_url')"
        seen_at="$(printf '%s' "$source" | jq -r '.seen_at')"

        output+=$'\n'
        output+="- [$source_key]($pr_url)"
        if [[ -n "$run_url" ]]; then
            output+=" via [workflow run]($run_url)"
        fi
        output+=" first observed at $seen_at"

        while IFS= read -r finding; do
            local path line summary review_url

            path="$(printf '%s' "$finding" | jq -r '.path')"
            line="$(printf '%s' "$finding" | jq -r '.line // "-"')"
            summary="$(printf '%s' "$finding" | jq -r '.summary')"
            review_url="$(printf '%s' "$finding" | jq -r '.review_url')"
            output+=$'\n'
            output+="  - [$path:$line]($review_url) - $summary"
        done < <(printf '%s' "$source" | jq -c '.findings[]')
    done < <(printf '%s' "$state_json" | jq -c '
        .sightings
        | sort_by(.source_key, .review_url)
        | group_by(.source_key)[]
        | {
            source_key: .[0].source_key,
            pr_url: .[0].pr_url,
            run_url: ([.[].run_url] | map(select(length > 0)) | last // ""),
            seen_at: ([.[].seen_at] | min),
            findings: map({path, line, summary, review_url})
          }')

    printf '%s\n' "$output"
}

find_tracking_issue_json() {
    local repo="$1"
    local title="$2"

    PAGER=cat GH_PAGER=cat gh issue list --repo "$repo" --state open --limit 100 --search "\"$title\" in:title" --json number,title,url \
        | jq -c --arg title "$title" 'map(select(.title == $title)) | first // empty'
}

write_issue_body_file() {
    local body="$1"
    local body_file

    body_file="$(mktemp)"
    printf '%s\n' "$body" >"$body_file"
    printf '%s\n' "$body_file"
}

sync_tracking_issue() {
    local tracking_repo="$1"
    local state_json="$2"
    local threshold="$3"
    local dry_run="$4"
    shift 4
    local labels=("$@")
    local title issue_json issue_number issue_url existing_body existing_state merged_state existing_compact merged_compact distinct_prs body body_file args

    title="Copilot Learning: $(printf '%s' "$state_json" | jq -r '.category')"
    issue_json="$(find_tracking_issue_json "$tracking_repo" "$title")"
    issue_number="$(printf '%s' "$issue_json" | jq -r '.number // empty')"
    issue_url="$(printf '%s' "$issue_json" | jq -r '.url // empty')"

    if [[ -n "$issue_number" ]]; then
        existing_body="$(PAGER=cat GH_PAGER=cat gh issue view "$issue_number" --repo "$tracking_repo" --json body | jq -r '.body')"
        existing_state="$(extract_tracker_state "$existing_body")"
    else
        existing_state='{}'
    fi

    merged_state="$(merge_tracker_state "$existing_state" "$state_json")"
    distinct_prs="$(printf '%s' "$merged_state" | jq '[.sightings[].source_key] | unique | length')"
    existing_compact="$(printf '%s' "$existing_state" | jq -c '.')"
    merged_compact="$(printf '%s' "$merged_state" | jq -c '.')"

    if [[ -z "$issue_number" && "$distinct_prs" -lt "$threshold" ]]; then
        printf -- '- Below threshold: %s (%s/%s distinct PRs)\n' "$title" "$distinct_prs" "$threshold"
        return
    fi

    if [[ -n "$issue_number" && "$existing_compact" == "$merged_compact" ]]; then
        printf -- '- No change: %s\n' "$issue_url"
        return
    fi

    body="$(render_tracker_issue_body "$merged_state")"

    if [[ "$dry_run" == "true" ]]; then
        if [[ -n "$issue_number" ]]; then
            printf -- '- Dry run update: %s\n' "$issue_url"
        else
            printf -- '- Dry run create: %s\n' "$title"
        fi
        return
    fi

    body_file="$(write_issue_body_file "$body")"

    if [[ -n "$issue_number" ]]; then
        args=(issue edit "$issue_number" --repo "$tracking_repo" --body-file "$body_file")
        for label in "${labels[@]}"; do
            args+=(--add-label "$label")
        done
        gh "${args[@]}" >/dev/null
        rm -f "$body_file"
        printf -- '- Updated tracking issue: %s\n' "$issue_url"
        return
    fi

    args=(issue create --repo "$tracking_repo" --title "$title" --body-file "$body_file")
    for label in "${labels[@]}"; do
        args+=(--label "$label")
    done
    issue_url="$(gh "${args[@]}")"
    rm -f "$body_file"
    printf -- '- Created tracking issue: %s\n' "$issue_url"
}

fetch_threads_json() {
    local repo="$1"
    local pr_number="$2"
    local query
    local response

    split_repo "$repo"
    query=$(cat <<'EOF'
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100) {
                pageInfo {
                    hasNextPage
                }
        nodes {
          id
          isResolved
          path
          line
          comments(first:20) {
                        pageInfo {
                            hasNextPage
                        }
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

    response="$(PAGER=cat GH_PAGER=cat gh api graphql \
        -F owner="$REPO_OWNER" \
        -F name="$REPO_NAME" \
        -F number="$pr_number" \
        -f query="$query")"

    if printf '%s' "$response" | jq -e '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage or any(.data.repository.pullRequest.reviewThreads.nodes[]?; .comments.pageInfo.hasNextPage)' >/dev/null; then
        echo "Warning: Copilot review export for $repo PR #$pr_number was truncated by GitHub pagination limits." >&2
    fi

    printf '%s\n' "$response"
}

list_open_prs_json() {
    local repo="$1"
    local max_prs="$2"

    PAGER=cat GH_PAGER=cat gh pr list --repo "$repo" --state open --limit "$max_prs" --json number,title,url,isDraft
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
    local max_prs="$3"
    local output_dir="$4"
    local pr_list repo_dir total found summary

    pr_list="$(list_open_prs_json "$repo" "$max_prs")"
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
        render_findings_jsonl "$repo" "$pr_number" "$pr_url" "$state" "$threads_json" >"$prefix-findings.jsonl"
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
            --repo) require_value "$1" "${2:-}"; repo="$2"; shift 2 ;;
            --pr) require_value "$1" "${2:-}"; pr_number="$2"; shift 2 ;;
            --state) require_value "$1" "${2:-}"; state="$2"; validate_state "$state"; shift 2 ;;
            --format) require_value "$1" "${2:-}"; format="$2"; validate_format "$format"; shift 2 ;;
            --output) require_value "$1" "${2:-}"; output_file="$2"; shift 2 ;;
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
            --repo) require_value "$1" "${2:-}"; repo="$2"; shift 2 ;;
            --pr) require_value "$1" "${2:-}"; pr_number="$2"; shift 2 ;;
            --state) require_value "$1" "${2:-}"; state="$2"; validate_state "$state"; shift 2 ;;
            --output) require_value "$1" "${2:-}"; output_file="$2"; shift 2 ;;
            *) echo "Unknown option for lessons: $1" >&2; usage; exit 1 ;;
        esac
    done

    [[ -n "$repo" && -n "$pr_number" ]] || { echo "lessons requires --repo and --pr" >&2; usage; exit 1; }
    threads_json="$(fetch_threads_json "$repo" "$pr_number" | filter_threads "$state")"
    write_output "$(render_lessons_markdown "$repo" "$pr_number" "$state" "$threads_json")" "$output_file"
}

command_scan() {
    local repos=() state="unresolved" max_prs="100" output_dir="copilot-review-memory" summary

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) require_value "$1" "${2:-}"; repos+=("$2"); shift 2 ;;
            --state) require_value "$1" "${2:-}"; state="$2"; validate_state "$state"; shift 2 ;;
            --max-prs) require_value "$1" "${2:-}"; max_prs="$2"; validate_positive_integer "--max-prs" "$max_prs"; shift 2 ;;
            --output-dir) require_value "$1" "${2:-}"; output_dir="$2"; shift 2 ;;
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
        summary+="$(scan_repo "$repo" "$state" "$max_prs" "$output_dir")"
    done

    printf '%s\n' "$summary" >"$output_dir/summary.md"
    cat "$output_dir/summary.md"
}

command_track() {
    local tracking_repo="" input_dir="copilot-review-memory" threshold="2" output_file="" run_url="" dry_run="false"
    local labels=()
    local findings_json grouped summary finding_count category_count

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) require_value "$1" "${2:-}"; tracking_repo="$2"; shift 2 ;;
            --input-dir) require_value "$1" "${2:-}"; input_dir="$2"; shift 2 ;;
            --threshold) require_value "$1" "${2:-}"; threshold="$2"; validate_positive_integer "--threshold" "$threshold"; shift 2 ;;
            --label) require_value "$1" "${2:-}"; labels+=("$2"); shift 2 ;;
            --run-url) require_value "$1" "${2:-}"; run_url="$2"; shift 2 ;;
            --output) require_value "$1" "${2:-}"; output_file="$2"; shift 2 ;;
            --dry-run) dry_run="true"; shift ;;
            *) echo "Unknown option for track: $1" >&2; usage; exit 1 ;;
        esac
    done

    [[ -n "$tracking_repo" ]] || { echo "track requires --repo" >&2; usage; exit 1; }
    findings_json="$(load_findings_json "$input_dir")"
    finding_count="$(printf '%s' "$findings_json" | jq 'length')"
    grouped="$(printf '%s' "$findings_json" | jq 'sort_by(.category_key) | group_by(.category_key)')"
    category_count="$(printf '%s' "$grouped" | jq 'length')"
    summary="# Copilot Review Tracking

- Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- Tracking repository: $tracking_repo
- Threshold: $threshold
- Findings loaded: $finding_count
- Categories loaded: $category_count
- Dry run: $dry_run"

    if [[ "$finding_count" == "0" ]]; then
        summary+=$'\n\n- No findings artifacts were available for tracking.'
        write_output "$summary" "$output_file"
        return
    fi

    while IFS= read -r group; do
        local state_json result_line

        state_json="$(build_tracker_state "$group" "$threshold" "$run_url")"
        result_line="$(sync_tracking_issue "$tracking_repo" "$state_json" "$threshold" "$dry_run" "${labels[@]}")"
        summary+=$'\n'
        summary+="$result_line"
    done < <(printf '%s' "$grouped" | jq -c '.[]')

    write_output "$summary" "$output_file"
}

command_resolve() {
    local thread_ids=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --thread-id) require_value "$1" "${2:-}"; thread_ids+=("$2"); shift 2 ;;
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
        track) command_track "$@" ;;
        resolve) command_resolve "$@" ;;
        --help|-h|help) usage ;;
        *) echo "Unknown subcommand: $subcommand" >&2; usage; exit 1 ;;
    esac
}

main "$@"

# Issue tracker: GitHub Issues

The canonical [PRD](../PRD.md) and [decision record](../decisions.md) live in Git. GitHub Issues track bounded work, blockers, and owner decisions. Do not make a second competing spec in an issue body.

## Conventions

- One issue per verifiable outcome. Link the relevant PRD section and acceptance gate.
- State prerequisites, owner inputs, expected evidence, and dependencies. Use the issue templates.
- Use `needs-info` for a missing owner/external input, `ready-for-agent` for a bounded task with its prerequisites, `ready-for-human` when the operator must act, and `wontfix` for rejected work. See [triage labels](triage-labels.md).
- A `Decision:` issue records a proposed change to scope, quality rules, UI wording/layout, external spend, or acceptance. An agent may recommend but must not silently make that call.
- Close an issue with a PR or evidence link and the outcome. Keep secrets, class content, and student information out of issue bodies and comments.

## When a skill says “publish to the issue tracker”

Create a GitHub Issue in this repository. For a PRD, link the canonical versioned document and include the problem, solution, main stories, acceptance link, and dependency status. The PRD file remains authoritative.

## When a skill says “fetch the relevant ticket”

Use the issue URL or number, then read the linked PRD and decision record before work. Older `.scratch/` conventions are retired for this repository.

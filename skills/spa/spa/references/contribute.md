# Contribute to spa (parent checklist)

Load this only when changing the SPA framework, not for a lab or environment. Full procedure: [docs/architecture.md](../../../../docs/architecture.md#feature-development-lifecycle).

## Before production edits

1. Fetch and update the recorded base branch. Never assume `distribution` or `master`.
2. Create a dedicated feature branch.
3. Record that base.

A plan, a todo list, or an implement-this request does not skip these steps.

## TDD

For each behavior, add one test, run it alone, and see it fail before changing production code. Regenerated catalogs (`spa --no-agent agent schema --markdown`, `spa --no-agent config schema --markdown`) only after the drift test has failed. Close the slice on the required local gates (the new test, tests for every touched module, and `./tests/run_cli_tests.sh` when parser, help, routing, schema, session, or provider contracts changed). PR CI runs the full suite.

Full procedure: [Test-driven development](../../../../docs/architecture.md#test-driven-development).

## Completion review (parent only)

The parent agent writes the report. Do not spawn a second agent to re-run tests.

For each finding: what was found, what was fixed, and what was left out. Wait for the user to confirm the left-out items, then ask whether to commit. Then ask before a pull request, and again before merge. After merge succeeds, close the linked issue with a short note naming the PR and commit (GitHub will not auto-close on `distribution`).

Completing todos is not authorization to implement, commit, or merge.

Full procedure: [Feature completion review](../../../../docs/architecture.md#feature-completion-review).

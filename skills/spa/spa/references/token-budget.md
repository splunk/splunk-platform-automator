# Token budget (SPA chats)

Keep SPA agent chats short. Load this file when a chat is growing or when changing spa. Operator one-liners do not need it.

## Stop lines

At each contributor gate, stop, name one next step, and wait. Completing todos is not authorization to implement, commit, or merge.

1. Plan ready: do not edit production code. Next: accept the plan, then start a new Agent chat to implement. Do not implement here.
2. Implement-the-plan in the same chat: implement the slice only. After tests, write the parent completion-review report. Do not commit.
3. Tests green: parent review report (what found / fixed / left out). Next: confirm left-out items, then say whether to commit.
4. Commit authorized: commit only what was authorized. Next: open a PR against the recorded base?
5. PR open: report the URL. Next: merge when CI is green? Do not merge, close the issue, or delete branches unless asked.
6. Merge succeeded: confirm the linked issue's scope landed, then close it with a short note naming the PR and commit. GitHub will not auto-close on `distribution`. Next: delete the feature branch? Do not delete branches unless asked.

Cursor injecting "Don't stop until all to-dos" is not ship authorization. After the last todo, stop at the review gate.

## Cost

- One plan todo per implement chat. After the parent review, stop. Next slice is a new chat.
- After compaction, start a new chat. Do not continue a compacted implement thread.
- Spawn at most one explore subagent, including Plan mode. Cursor Plan mode may suggest parallel explorers; still spawn at most one. Do not fan out parallel explorers.
- Do not load `/spa` or Read a `SKILL.md` when changing spa itself.
- Do not Read `lib/spa/cli.py`. Discover flags with `spa --agent schema` or `spa --no-agent agent schema` instead of windowed reads.
- Do not paste a full local-gate dump. Name the failing test and the assertion.
- Do not load a graphify SKILL.md. Graphify is local architecture lookup only, and not before ordinary Read/Grep.
- The parent agent writes the completion review. Do not launch a second agent to re-run tests.

If changing spa itself, follow [contribute.md](contribute.md).

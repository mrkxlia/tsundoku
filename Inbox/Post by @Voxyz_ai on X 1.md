https://x.com/voxyz_ai/status/2086059460502417772?s=12&t=22GY_jUSQsg0NcuE2S9fmA
# Post by @Voxyz_ai on X
2026-08-11
𝗛𝗲𝗿𝗱𝗿 has been great these past few days.

Claude and Codex each get a pane. The main agent assigns work, waits, reads, and follows up. I used to carry every conclusion between windows myself.

With ChatGPT, Codex, and other agents, one works and another reviews.

𝗣𝗿𝗼𝗺𝗽𝘁:

Run this task with multiple agents in parallel:

\[TASK\]

You are the coordinator. Check which agents and panes are available, then split the task only where pieces can move independently.

Give each agent one clear outcome. State the deliverable, how it will be checked, what it may change, and what it must not touch.

Research and review agents may share the current workspace, but they must stay read-only. For work inside a Git repo, give every agent that edits files its own worktree so no two writers share a checkout.

Use Herdr to assign work to the other panes, wait for their results, read their output, and follow up yourself. Do not ask me to relay messages.

When different agents are available, have one execute and another review. Swap roles on the next pass if useful. Settle factual disagreements with a test. You decide judgment calls.

Bring the work together in one place. For a Git repo, integrate through one checkout and rerun the real checks. Do not push, publish, touch production, or expose secrets without my approval.

Finish with the result, verification evidence, unresolved issues, and any panes or worktrees still running.
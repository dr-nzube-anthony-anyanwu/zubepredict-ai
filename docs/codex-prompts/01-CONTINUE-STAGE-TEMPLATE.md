# Codex continuation prompt

Replace `[N]` and `[NAME]`, then paste this into Codex after the previous stage passes.

```text
Continue ZubePredict AI with Stage [N]: [NAME].

First inspect the current repository, README, build roadmap, master prompt, git status and the previous stage's tests. Preserve existing work. Before editing, give me the stage goal, expected files, proof tests and any account variables needed.

Implement only this stage. Follow every engineering invariant and exit gate in docs/codex-prompts/00-MASTER-PROMPT.md. Add or update automated tests, run Ruff, pytest and any relevant frontend/Docker checks, and repair failures before reporting completion.

Do not expose or commit secrets. Do not begin the next stage. Finish with the required seven-section stage report from the master prompt, and explain my own next steps in very simple numbered instructions.
```


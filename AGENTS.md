MUST read `docs/ARCHITECTURE.md` and `docs/CONTEXT.md`.
Main goal: cover E2E AI PDLC engineering workflows at foundation level.
Monorepo with multiple solution components in `src` and golden instructions in `instructions`. R3 is current, R2 is KTLO.
Defines reusable plugins/mcp for AI coding agents (claude code, codex, copilot, cursor, antigravity, etc) which users (engineers, developers) invoke on THEIR target repositories.
`instructions` folder contains AI coding agent **instructions** for another repository (skills, subagents, rules, workflows), it is **not documentation**. 
AI Coding Agents always load `instructions/r3/core/rules/bootstrap-alwayson.md` and one mode-specific file (plugin-files-mode.md, mcp-files-mode.md, local-files-mode.md).

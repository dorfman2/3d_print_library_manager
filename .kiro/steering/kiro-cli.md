---
inclusion: manual
---

# Kiro CLI — Agent Reference

## spec-executor Agent

Workspace-local agent at `.kiro/agents/spec-executor.json`. Autonomous task executor that reads a spec's `tasks.md`, implements each task sequentially, verifies via build/test, and marks tasks complete. Does NOT design or plan.

### Usage

**Execute all tasks in a spec:**
```bash
kiro-cli chat --agent spec-executor --trust-all-tools "Execute all tasks in .kiro/specs/<spec-name>/tasks.md"
```

**Resume after a failure or interruption:**
```bash
kiro-cli chat --agent spec-executor --trust-all-tools --resume
```

**Run with TUI for better visibility:**
```bash
kiro-cli chat --agent spec-executor --trust-all-tools --tui "Execute all tasks in .kiro/specs/<spec-name>/tasks.md"
```

**Headless/CI mode (no user prompts):**
```bash
kiro-cli chat --agent spec-executor --trust-all-tools --no-interactive "Execute all tasks in .kiro/specs/<spec-name>/tasks.md"
```

**Override model:**
```bash
kiro-cli chat --agent spec-executor --trust-all-tools --model claude-sonnet-4 "Execute all tasks in .kiro/specs/<spec-name>/tasks.md"
```

### Flags reference
| Flag | Purpose |
|------|---------|
| `--agent spec-executor` | Use the spec-executor agent |
| `--trust-all-tools` / `-a` | Full autonomy, no tool-approval prompts |
| `--no-interactive` | No user input expected (CI/headless) |
| `--resume` | Resume most recent conversation |
| `--resume-picker` | Pick a specific conversation to resume |
| `--model <model>` | Override model (e.g. `--model claude-sonnet-4`) |
| `--tui` | Nicer terminal UI with panels |

### Typical Workflow

1. **Create spec** in Kiro IDE (Spec mode) — produces `requirements.md`, `design.md`, `tasks.md`
2. **Execute tasks** via kiro-cli:
   ```bash
   kiro-cli chat --agent spec-executor --trust-all-tools "Execute all tasks in .kiro/specs/<spec-name>/tasks.md"
   ```
3. **If interrupted**, resume:
   ```bash
   kiro-cli chat --agent spec-executor --trust-all-tools --resume
   ```
4. **Review results** — check git diff, run tests manually if needed

### Performance Notes
- kiro-cli is typically ~2-3x cheaper in credits and ~5-8x faster than executing tasks in Kiro Chat
- Use `--trust-all-tools` to avoid approval prompts that slow execution
- The agent reads `.kiro/steering/` automatically for project conventions

### Behavior
1. Finds next `- [ ]` task in `tasks.md` (respects dependency order)
2. Reads `design.md` + `requirements.md` + `.kiro/steering/` for context
3. Implements the task (writes code, modifies files)
4. Runs build/test verification
5. On pass: marks `- [x]` in `tasks.md`, moves to next
6. On fail: one retry. If second attempt fails, STOPS and reports diagnostics
7. Never modifies `requirements.md` or `design.md`

### Tools granted
`read`, `write`, `shell`, `grep`, `glob`, `thinking`, `delegate`

No MCP servers included by default. Set `includeMcpJson: true` in the agent JSON to enable project MCP tools.

## Built-in Agents
| Agent | Purpose |
|-------|---------|
| `kiro_default` | General-purpose (default) |
| `kiro_help` | Answers Kiro CLI questions from docs |
| `kiro_planner` | Breaks ideas into implementation plans |

## Agent Management
```
kiro-cli agent list                    # show all agents (global + workspace)
kiro-cli agent create <name>           # interactive create
kiro-cli agent create <name> -d .kiro/agents  # workspace-local agent
kiro-cli agent edit <name>             # edit existing config
kiro-cli agent set-default <name>      # change default agent
kiro-cli agent validate <path>         # validate config JSON
```

## Chat Commands
```
kiro-cli chat "prompt"                 # one-shot question (default agent)
kiro-cli chat --tui                    # interactive TUI mode
kiro-cli chat --resume                 # resume last conversation
kiro-cli chat --resume-picker          # pick a conversation to resume
kiro-cli chat -l                       # list saved sessions
kiro-cli chat --list-models            # show available models
```

## Agent Config Schema
```json
{
  "name": "agent-name",
  "description": "What this agent does",
  "prompt": "System prompt with execution instructions",
  "tools": ["read", "write", "shell", "grep", "glob", "thinking", "delegate"],
  "mcpServers": {},
  "allowedTools": [],
  "resources": [],
  "hooks": {},
  "toolAliases": {},
  "toolsSettings": {},
  "includeMcpJson": false,
  "model": null
}
```

### Tool categories
- `read` — file reading
- `write` — file creation/editing
- `shell` — terminal command execution
- `grep` — text search (ripgrep-based)
- `glob` — file path matching
- `thinking` — extended reasoning
- `delegate` — sub-agent delegation
- `aws` — AWS service tools
- `report` — reporting/output tools
- `introspect` — self-inspection
- `knowledge` — knowledge base access
- `todo` — task tracking
- `@server/tool` — specific MCP tool
- `@server` — all tools from an MCP server
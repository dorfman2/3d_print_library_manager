---
inclusion: manual
---

# Kiro CLI — Agents and Spec Executor

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

### Tools enabled
`read`, `write`, `shell`, `grep`, `glob`, `thinking`, `delegate`

No MCP servers included by default. To add MCP access, set `"includeMcpJson": true` in the agent JSON.

## Other Built-in Agents
- `kiro_default` — general-purpose (default)
- `kiro_help` — answers Kiro CLI questions
- `kiro_planner` — breaks ideas into implementation plans

## Agent Management Commands
```
kiro-cli agent list                    # show all agents
kiro-cli agent create <name>           # interactive create
kiro-cli agent create <name> -f <base> # create from existing agent as template
kiro-cli agent edit <name>             # edit existing
kiro-cli agent set-default <name>      # change default
kiro-cli agent validate <path>         # validate config JSON
```

## Chat Commands
```
kiro-cli chat "prompt"                         # one-shot with default agent
kiro-cli chat --agent <name> "prompt"          # use specific agent
kiro-cli chat --resume                         # resume last conversation
kiro-cli chat --resume-picker                  # pick conversation to resume
kiro-cli chat -l                               # list saved sessions
kiro-cli chat --list-models                    # show available models
kiro-cli chat --tui                            # terminal UI mode
```

## Agent Config Schema (`~/.kiro/agents/<name>.json`)
```json
{
  "name": "agent-name",
  "description": "What this agent does",
  "prompt": "System prompt with execution instructions",
  "tools": ["read", "write", "shell", "grep", "glob", "thinking", "delegate"],
  "mcpServers": {},
  "toolAliases": {},
  "allowedTools": [],
  "resources": [],
  "hooks": {},
  "toolsSettings": {},
  "includeMcpJson": false,
  "model": null
}
```

### Available tool categories
`read`, `write`, `shell`, `aws`, `report`, `introspect`, `knowledge`, `thinking`, `todo`, `delegate`, `grep`, `glob`, `@mcp_server_name/tool_name`, `@mcp_server_name` (all tools from that server)
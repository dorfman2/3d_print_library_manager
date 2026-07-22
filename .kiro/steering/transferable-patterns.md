---
inclusion: always
---

# Transferable Analysis Patterns
**Purpose**: Mandatory standards for identifying and documenting reusable analysis patterns across multiple projects

## Pattern Recognition
You **MUST** identify patterns that demonstrate broad applicability when you discover effective search commands that could work across multiple projects.
You **MUST** recognize transferable methodologies when you develop analysis approaches that aren't specific to the current technology stack or vulnerability type.
You **MUST** distinguish between project-specific findings and generalizable techniques.
You **MUST** evaluate pattern effectiveness based on whether the technique successfully identifies security-relevant code patterns, configuration issues, or architectural concerns.

## Documentation Requirements
You **MUST** document transferable patterns in `tech-context.md` under appropriate sections.
You **MUST** include the complete command syntax with explanations when documenting command-line patterns.
You **MUST** provide context about when and why to use each pattern.
You **MUST** organize patterns by category (search patterns, analysis techniques, tool usage, etc.).

## Documentation Format
You **MUST** use the following format when adding patterns:

```markdown
### [Pattern Category]

#### [Pattern Name]
- **Command**: `exact command syntax`
- **Purpose**: Brief description of what this finds/accomplishes
- **Use Case**: When to apply this pattern
- **Example**: Sample output or usage scenario
- **Notes**: Any important considerations or variations
```

## Pattern Validation
You **MUST** theoretically walk through several scenarios with patterns on multiple file types or project structures before documenting them.
You **MUST** update patterns when you discover improvements or edge cases.

## Pattern Evolution
You **MUST** refine patterns based on experience across multiple projects.
You **MUST** remove or deprecate patterns that prove ineffective or unreliable.
You **MUST** version or date significant pattern updates so that the evolution of techniques can be tracked.

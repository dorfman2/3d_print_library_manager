---
inclusion: always
---

# Code Analysis Requirements
**Purpose**: Mandatory standards for security-focused code analysis and evidence collection

## Evidence Requirements
You **MUST** include line numbers in all code snippets.
You **MUST** provide exact evidence from source code with:
- File path
- Line start and end numbers
- Language-tagged code blocks with line numbers
You **MUST NOT** make assumptions without code evidence.

## Analysis Standards
You **MUST** identify logical and flow inconsistencies in system behavior.
You **MUST** analyze actual vulnerabilities without contriving non-existent issues.
You **MUST** exclude `.venv`, `node_modules`, and similar dependency directories from analysis unless those locations are specifically warranted.

## Reporting Format
Evidence **MUST** follow this structure:
```
File: <path>
Line Start: <int>
Line End: <int>
```<language>
line# code
line# code
```
```

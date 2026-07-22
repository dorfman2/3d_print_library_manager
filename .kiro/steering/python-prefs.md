---
inclusion: fileMatch
fileMatchPattern: "**/*.py"
---

# Python Coding Preferences
**Purpose**: Mandatory Python coding standards and practices for security-focused development

## Testing Requirements
You **MUST NOT** use mock, patch, or similar test isolation capabilities. All tests **MUST** use real implementations and actual system interactions.
You **MUST** write integration tests that exercise actual code paths with real dependencies.
You **MUST** validate actual system behavior rather than mocked responses.

## Documentation Requirements
You **MUST** provide verbose docstrings for all:
- Modules
- Classes
- Functions
- Methods (excluding helper methods with naming pattern `method.helper_method`)
You **MUST** include in docstrings:
- Purpose and behavior description
- Parameter types and descriptions
- Return value types and descriptions
- Raised exceptions
- Usage examples where appropriate

## Type Safety Requirements
You **MUST** use type hints on all function signatures, method signatures, and class attributes.
You **MUST** define explicit data structures using dataclasses, NamedTuple, or TypedDict rather than generic dictionaries or tuples.
You **MUST** specify return types for all functions and methods.

## Code Style Requirements
You **MUST** follow all PEP standards including but not limited to:
- PEP 8 (Style Guide)
- PEP 257 (Docstring Conventions)
- PEP 484 (Type Hints)
- PEP 526 (Variable Annotations)
You **MUST** maintain consistent formatting throughout codebase.

## Quality Assurance Requirements
You **MUST** run linting tools on all Python code before task completion.
You **MUST** remediate all linting issues identified.
You **SHALL** use tools such as:
- `flake8` or `ruff` for style checking
- `mypy` for type checking
- `black` for code formatting
- `isort` for import sorting

## Final Note
No task involving Python code **SHALL** be considered complete until linting passes without errors or warnings.

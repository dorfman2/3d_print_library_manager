---
inclusion: fileMatch
fileMatchPattern: "**/*.py"
---

# Logging Standards and Requirements
**Purpose**: Mandatory standards for logging usage and lazy string formatting in error reporting

## Logging vs Print Requirements
You **MUST** use logging facilities instead of print statements for all error reporting, warnings, and informational messages.
You **MUST** reserve print statements only for:
- Direct user output that is part of the program's primary function
- CLI help text and version information
- Progress indicators that must appear on stdout
- Final results that users expect to see
You **MUST NOT** use print statements for:
- Error messages and warnings
- Long-term debug information
- Status updates during processing
- Configuration loading messages
- Internal process information

## Lazy String Formatting Requirements
You **MUST** use lazy string formatting with logging methods instead of f-strings or string concatenation.
You **MUST** use this pattern for all logging calls:
```python
# Correct - lazy formatting
logger.error("Failed to process file %s: %s", filename, error_message)
logger.info("Processing %d items from %s", count, source)
logger.warning("Configuration missing key %s, using default %s", key, default_value)

# Incorrect - eager formatting
logger.error(f"Failed to process file {filename}: {error_message}")
logger.info("Processing {} items from {}".format(count, source))
logger.warning("Configuration missing key " + key + ", using default " + str(default_value))
```

## Log Level Guidelines
You **MUST** use appropriate log levels:
- **ERROR**: Failures that prevent operation completion
- **WARNING**: Issues that don't prevent operation but indicate problems
- **INFO**: Important operational information and status updates
- **DEBUG**: Detailed diagnostic information for troubleshooting

## Logger Setup Requirements
You **MUST** create module-level loggers using:
```python
import logging
logger = logging.getLogger(__name__)
```
You **MUST NOT** use the root logger directly except for initial configuration.

## Migration Requirements
You **MUST** replace print statements with appropriate logging calls during code updates.
You **MUST** convert f-strings and string concatenation to lazy formatting when updating logging calls.
You **MUST** ensure all error conditions use logger.error() or logger.warning() instead of print().

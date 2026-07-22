---
inclusion: fileMatch
fileMatchPattern: "**/*.{js,ts,jsx,tsx,mjs,cjs}"
---

# JavaScript Logging Standards and Requirements
**Purpose**: Mandatory standards for JavaScript logging usage and structured logging in browser extensions and Node.js applications

## Logging vs Console Requirements
You **MUST** use structured logging facilities instead of console methods for all error reporting, warnings, and informational messages in production code.
You **MUST** reserve console methods only for:
- Direct user output that is part of the program's primary function
- Development debugging that **MUST** be removed before production
- Browser extension development where console is the primary logging mechanism
- CLI help text and version information in Node.js applications
You **MUST NOT** use console methods for:
- Error messages and warnings in production applications
- Long-term debug information
- Status updates during processing
- Configuration loading messages
- Internal process information

## Structured Logging Requirements
You **MUST** use structured logging with proper log levels and contextual data.
You **MUST** use this pattern for all logging calls:
```javascript
// Correct - structured logging with context
logger.error('Failed to process file', { filename, error: error_message });
logger.info('Processing items', { count, source });
logger.warn('Configuration missing key, using default', { key, default_value });

// Incorrect - console with string concatenation
console.error(`Failed to process file ${filename}: ${error_message}`);
console.info(`Processing ${count} items from ${source}`);
console.warn('Configuration missing key ' + key + ', using default ' + default_value);
```

## Lazy Evaluation Requirements
You **MUST** use lazy evaluation patterns to prevent runtime errors:
```javascript
// Correct - lazy evaluation with fallback
logger.error('Error processing file', { 
  filename: filename || 'UNKNOWN',
  error: error?.message || 'Unknown error'
});

// Incorrect - eager evaluation that could crash
logger.error('Error processing file', { filename, error: error.message });
```

## Log Level Guidelines
You **MUST** use appropriate log levels:
- **fatal/error**: Failures that prevent operation completion
- **warn**: Issues that don't prevent operation but indicate problems
- **info**: Important operational information and status updates
- **debug**: Detailed diagnostic information for troubleshooting
- **trace**: Very detailed diagnostic information with stack traces

## Logger Setup Requirements
For Node.js applications, you **MUST** create module-level loggers using a recognized framework:
```javascript
// Using Pino (recommended)
const pino = require('pino');
const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  timestamp: pino.stdTimeFunctions.isoTime
});

// Using Winston
const winston = require('winston');
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [new winston.transports.Console()]
});
```

For browser extensions, you **MAY** create a simple logging wrapper:
```javascript
const logger = {
  error: (msg, data) => console.error(msg, data),
  warn: (msg, data) => console.warn(msg, data),
  info: (msg, data) => console.info(msg, data),
  debug: (msg, data) => console.debug(msg, data)
};
```

## Security Requirements
You **MUST** ensure sensitive data stays out of logs:
```javascript
// Use redaction for sensitive fields
const logger = pino({
  redact: ['password', 'token', 'apiKey', 'creditCard']
});
```

## Error Logging Requirements
You **MUST** log errors with stack traces:
```javascript
try {
  // risky operation
} catch (error) {
  logger.error('Operation failed', {
    error: error.message,
    stack: error.stack,
    operation: 'file_upload',
    userId: currentUser.id
  });
}
```

## Migration Requirements
You **MUST** replace console statements with appropriate logging calls during code updates.
You **MUST** convert template literals and string concatenation to structured logging with context objects.
You **MUST** ensure all error conditions use logger.error() or logger.warn() instead of console methods.

## Framework Recommendations
You **SHOULD** use these logging frameworks for different environments:
- **Node.js Production**: Pino (performance) or Winston (features)
- **Node.js Development**: Pino with pino-pretty
- **Browser Extensions**: Custom console wrapper with structured data
- **Frontend Applications**: Browser-compatible logging libraries like loglevel or debug

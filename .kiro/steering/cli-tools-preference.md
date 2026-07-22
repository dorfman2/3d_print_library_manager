---
inclusion: manual
---

# CLI Tools Preference and Reference
**Purpose**: Reference for command-line tools used in text manipulation, data processing, and analysis

## Essential CLI Tools Reference

### Text Search and Pattern Matching
1. **grep** - Pattern searching with regex support
   - `grep -n "pattern" file` (show line numbers)
   - `grep -r "pattern" dir/` (recursive search)
   - `grep -E "regex" file` (extended regex)
1. **ripgrep (rg)** - Ultra-fast text search
   - `rg "pattern" --type py` (file type filtering)
   - `rg -n "pattern"` (line numbers)
   - `rg -A 3 -B 3 "pattern"` (context lines)

### Text Processing and Manipulation
1. **sed** - Stream editor for filtering and transforming text
   - `sed 's/old/new/g' file` (global substitution)
   - `sed -n '10,20p' file` (print specific lines)
   - `sed '/pattern/d' file` (delete matching lines)
1. **awk** - Pattern scanning and processing
   - `awk '{print $1}' file` (print first column)
   - `awk '/pattern/ {print NR, $0}' file` (line numbers for matches)
   - `awk -F: '{print $1}' /etc/passwd` (custom field separator)
1. **cut** - Extract columns from text
   - `cut -d: -f1 /etc/passwd` (extract first field)
   - `cut -c1-10 file` (extract characters 1-10)
1. **tr** - Translate or delete characters
   - `tr '[:lower:]' '[:upper:]'` (case conversion)
   - `tr -d '\n'` (remove newlines)
   - `tr -s ' '` (squeeze repeated spaces)
1. **sort** - Sort lines of text
   - `sort -n file` (numeric sort)
   - `sort -k2 file` (sort by second field)
   - `sort -u file` (unique sort)
1. **uniq** - Report or omit repeated lines
   - `uniq -c file` (count occurrences)
   - `uniq -d file` (show duplicates only)

### Data Structure Processing
1. **jq** - JSON processor
   - `jq '.key' file.json` (extract key)
   - `jq -r '.[] | .name'` (raw output, iterate array)
   - `jq 'map(select(.status == "active"))'` (filter objects)
1. **yq** - YAML/XML processor
   - `yq '.key' file.yaml` (extract YAML key)
   - `yq -o json file.yaml` (convert YAML to JSON)

### File Operations and Navigation
1. **find** - Search for files and directories
   - `find . -name "*.py" -type f` (find Python files)
   - `find . -mtime -7` (modified in last 7 days)
   - `find . -exec grep "pattern" {} \;` (execute command on results)
1. **fd** - Simple, fast alternative to find
   - `fd "pattern"` (find files matching pattern)
   - `fd -e py` (find by extension)
   - `fd -t f "config"` (find files only)

### Text Analysis and Statistics
1. **wc** - Word, line, character, and byte count
   - `wc -l file` (line count)
   - `wc -w file` (word count)
1. **nl** - Number lines of files
   - `nl -ba file` (number all lines)
1. **head/tail** - Output first/last part of files
   - `head -n 20 file` (first 20 lines)
   - `tail -n 20 file` (last 20 lines)
   - `tail -f file` (follow file changes)

### Data Conversion and Encoding
1. **base64** - Base64 encode/decode
   - `base64 file` (encode file)
   - `base64 -d encoded.txt` (decode)
1. **xxd** - Make a hexdump or reverse
   - `xxd file` (hex dump)
   - `xxd -r hexfile` (reverse hex dump)

### Network and System Analysis
1. **curl** - Transfer data from/to servers
   - `curl -s "url" | jq .` (fetch and parse JSON)
   - `curl -I "url"` (headers only)
   - `curl -X POST -d "data" "url"` (POST request)

## Example Pipeline Patterns
**Security Log Analysis**:
```bash
grep "ERROR" /var/log/auth.log | awk '{print $1, $2, $3, $9}' | sort | uniq -c | sort -nr
```
**Code Pattern Search**:
```bash
find . -name "*.py" -exec grep -l "password" {} \; | xargs grep -n "password" | cut -d: -f1,2
```
**JSON Data Processing**:
```bash
curl -s "api/endpoint" | jq '.results[]' | jq -r '.name + "," + .status' | sort
```

## Performance Considerations
You **SHOULD** prefer faster alternatives when processing large datasets:
- `ripgrep` over `grep` for large codebases
- `fd` over `find` for simple file searches
- `jq` over `awk` for JSON processing
- Compiled tools over interpreted scripts

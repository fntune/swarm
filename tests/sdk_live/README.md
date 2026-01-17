# SDK Live Tests

These are **manual integration tests** that make real API calls to Claude.

## Running

```bash
# Run individual test
python tests/sdk_live/test_sdk_live.py

# Run all requirements validation
python tests/sdk_live/test_sdk_requirements.py
```

## Requirements

- `claude-agent-sdk>=0.1.19` installed
- Valid API key configured
- Network access

## Note

These are NOT collected by pytest. They are standalone scripts for validating
SDK behavior against the live API.

# Game Query Discord Bot

## Installation

### `env` variables

### `systemd`

## Operations

### Add a server

### Edit a server

### Delete a server

## Development

### Running tests

Tests run offline with no real Discord/A2S/HTTP calls.

```bash
pip install -r requirements.txt
python -m pytest
```

Run a single file or test:

```bash
python -m pytest tests/test_server_embed.py
python -m pytest tests/test_server_embed.py::test_build_sets_update_true_when_status_differs_from_previous
```

Add `-v` for verbose output.


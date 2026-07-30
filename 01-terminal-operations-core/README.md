# Terminal Operations Core

Small Python domain model for terminal operations exercises.

## What It Includes

- Vessel validation rules
- Vessel lifecycle status transitions
- Dictionary and JSON serialization
- Pytest coverage for validation, transitions, and JSON round trips

## Project Structure

```text
.
├── main.py
├── src/
│   └── terminal_core/
│       ├── exceptions.py
│       └── vessel.py
├── tests/
│   └── test_vessel.py
└── data/
    └── vessel2.json
```

## Run The Demo

```bash
python main.py
```

## Run Tests

```bash
pytest
```

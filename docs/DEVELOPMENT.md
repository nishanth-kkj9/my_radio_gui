# Development Guide

This guide documents the repository's current development workflow and intentionally distinguishes what is automated today from what is still manual.

## Prerequisites

Install:

- Python 3.10+
- VLC Media Player
- Git

For Python tooling, the project declares `pytest` and `ruff` as development dependencies.

## Environment setup

```bash
python -m venv .venv
```

Activate the environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

Install the package with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Run the application

```bash
smart-radio-pro
```

or:

```bash
python src/smart_radio_pro/main.py
```

## Linting

The repository uses Ruff with a 100-character line length and Python 3.10 target:

```bash
ruff check src/
```

The same check runs in CI.

## Smoke testing

The current CI pipeline validates imports in a headless Linux environment:

```bash
QT_QPA_PLATFORM=offscreen python -c "from smart_radio_pro.core import config, theme, equalizer; print('Core modules OK')"
QT_QPA_PLATFORM=offscreen python -c "from smart_radio_pro.core.player import RadioPlayer; print('Player OK')"
```

On Windows, use your normal desktop environment when launching the GUI because a real display and VLC installation are expected.

## Automated test coverage: current state

The repository includes a `tests/` package and a `pytest` development dependency, but the tracked test tree currently contains only `tests/__init__.py`. There are no functional pytest test modules in the current revision.

As a result:

- **CI currently provides linting and import smoke coverage.**
- **End-to-end GUI behavior is not automatically tested.**
- **Playback/reconnect behavior still requires manual validation.**

Do not describe the repository as having a comprehensive automated test suite until actual test cases are added.

## Recommended test areas

When adding tests, prioritize:

1. URL validation and favicon sanitization.
2. Category cache and duplicate-fetch coordination.
3. JSON storage upgrades and corrupted-file recovery.
4. Playback statistics calculations.
5. Equalizer gain clamping and preset application.
6. Helper functions such as station-name cleaning and time formatting.
7. UI-independent logic that can run without a visible desktop.

Qt widget tests can be introduced later with a headless Qt test setup.

## Change workflow

A practical contributor workflow is:

```text
create branch
   │
   ├── make focused change
   ├── update docs/changelog
   ├── run ruff
   ├── run smoke checks
   └── open pull request
```

Keep unrelated refactors out of a focused change.

## Commit guidance

Use clear, imperative commit subjects, for example:

```text
Fix duplicate category fetches
Add architecture documentation
Improve VLC reconnect handling
Update installation instructions
```

Avoid vague subjects such as `changes`, `update`, or `fix stuff`.

## Documentation checklist

When behavior changes, review:

- `README.md`
- relevant file under `docs/`
- `CHANGELOG.md`
- keyboard-shortcut table if controls changed
- persistence/runtime-data documentation if stored state changed

## CI

The workflow in `.github/workflows/ci.yml` currently:

1. checks out the repository;
2. installs Python 3.11;
3. installs Linux Qt/VLC system dependencies;
4. installs the project with development dependencies;
5. runs `ruff check src/`;
6. runs two core/player import smoke tests.

The workflow is a quality gate, not full functional or packaging-release validation.

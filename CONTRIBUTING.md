# Contributing to Smart Radio Pro

Thank you for contributing. The project is small enough that focused changes, accurate documentation, and reproducible testing make a large difference.

## Before opening a change

Read:

- [`README.md`](README.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)

Understand which layer your change belongs to before modifying unrelated modules.

## Development principles

Prefer:

- small, focused changes;
- existing abstractions over duplicated logic;
- configuration through `core/config.py`;
- UI updates on the Qt main thread;
- background work for blocking network or I/O operations;
- atomic persistence writes;
- descriptive logging for recoverable failures;
- documentation that reflects actual code behavior.

Avoid:

- adding secrets or credentials;
- committing runtime JSON, databases, logs, build output, or virtual environments;
- blocking the Qt event loop with network/file operations;
- silently changing user-visible shortcuts;
- documenting features that are not implemented.

## Branching

Use a descriptive branch name, for example:

```text
docs/improve-repository-docs
fix/vlc-reconnect-state
feat/station-filtering
test/storage-roundtrip
```

## Code quality

Run:

```bash
ruff check src/
```

before opening a pull request.

Keep the existing Python 3.10 baseline unless the project is intentionally migrated.

## Testing

Run the available smoke checks:

```bash
python -c "from smart_radio_pro.core import config, theme, equalizer; print('Core modules OK')"
python -c "from smart_radio_pro.core.player import RadioPlayer; print('Player OK')"
```

Add regression tests when the behavior is suitable for unit testing. The current repository does not yet contain functional pytest cases, so do not rely on the empty `tests/` package as evidence of coverage.

## Documentation

Update documentation when you change:

- installation or dependencies;
- keyboard shortcuts;
- user-facing features;
- persistence files;
- configuration values;
- architecture or module boundaries;
- CI behavior.

Use `CHANGELOG.md` for meaningful user/developer-visible changes.

## Pull requests

A good PR should explain:

1. What changed.
2. Why it changed.
3. How it was tested.
4. Any known limitations or follow-up work.

Keep a pull request focused. Separate unrelated cleanup or redesign into another PR.

## Commit messages

Use short imperative subjects:

```text
Add station cache documentation
Fix reconnect state cleanup
Document runtime data files
```

## Security-sensitive changes

Do not disclose a vulnerability in a public issue. Follow [`SECURITY.md`](SECURITY.md).

## Code review

Reviewers should prioritize:

- correctness;
- regressions;
- thread safety;
- resource cleanup;
- user-visible behavior;
- security boundaries;
- documentation accuracy.

Style-only changes should not obscure functional changes.

# Project Documentation

This directory contains the maintained technical documentation for Smart Radio Pro.

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Module boundaries, data flow, threading, caching, startup/shutdown |
| [`CONFIGURATION.md`](CONFIGURATION.md) | Tunable constants, categories, cache limits, persistence |
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | Local setup, linting, smoke tests, CI, contribution workflow |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | VLC, network, cache, Qt, playback, and data recovery guidance |

The repository root [`README.md`](../README.md) is the primary user-facing entry point.

## Documentation rule

Documentation should describe behavior that exists in the current source tree. When code changes, update the relevant documentation and `CHANGELOG.md` in the same change.

## Source precedence

When documentation and implementation disagree, verify the executable source and packaging/CI configuration before editing prose.

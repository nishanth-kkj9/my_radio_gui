# Security Policy

## Supported version

The current `main` branch is the primary maintained development line.

Security fixes should be evaluated against the current code before assumptions are made about older revisions.

## Reporting a vulnerability

Please **do not open a public GitHub issue for an undisclosed security vulnerability**.

Use GitHub's private vulnerability reporting / security advisory workflow for this repository when it is available. If that workflow is unavailable, contact the maintainer privately through GitHub and provide enough information to reproduce and assess the issue.

Please include:

- affected component or file;
- reproduction steps;
- expected behavior;
- actual behavior;
- security impact;
- a minimal proof of concept when safe to share;
- the revision or commit you tested.

Avoid including real passwords, access tokens, private personal information, or unrelated sensitive data.

## Security-relevant design areas

The project already contains several defensive boundaries:

- stream URLs are checked against an explicit scheme allowlist before playback;
- HTTPS verification is enabled for HTTP requests;
- Radio Browser requests use timeouts and bounded retries;
- logo downloads have a byte limit;
- runtime state is stored locally rather than in a remote application backend;
- generated runtime artifacts are excluded from source control.

These controls are not a guarantee of security. They should be preserved when modifying network, persistence, or playback behavior.

## Safe development practices

Never commit:

- API keys;
- authentication tokens;
- passwords;
- local credential files;
- private URLs containing secrets;
- user runtime data.

When adding a dependency, review its purpose and licensing and avoid unnecessary packages.

## Security fixes

A security fix should normally include:

- the code change;
- a regression test when practical;
- documentation or changelog updates when behavior is user-visible;
- a concise explanation of the threat and mitigation in the pull request.

Please avoid publishing exploit details before a fix is available when the issue could affect other users.

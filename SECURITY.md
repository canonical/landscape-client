# Security policy

## Supported versions

LTS releases are published every two years, typically in April of even years.
Five point releases follow, typically in February and August. Standard support
is provided for 5 years and ESM support is provided for 12 years. These
releases are recommended for production.

Latest stable releases are published every six months, typically in April and
October. Support ends when the next release ships. Users must upgrade to
maintain support.

See [Supported versions and PPAs](https://ubuntu.com/landscape/docs/reference/supported-versions-and-ppas/)
for a list of currently supported versions of Landscape.

## What qualifies as a security issue

Please report issues that allow an attacker to affect the confidentiality,
integrity, or availability of Landscape or systems managed by Landscape beyond
the access and operations they are intended to have. Examples include:

- Authentication or authorization bypasses, including access to another
  account's data or the ability to perform an operation without the required
  permission.
- Cross-site request forgery (CSRF), injection, path traversal, or other attacks
  that allow unauthorized actions or data access.
- Denial-of-service vulnerabilities that can be triggered without the access or
  resources normally required for the affected operation.
- An internal service or administrative interface that is unintentionally
  reachable by an untrusted network or user.
- Insecure file permissions or secret exposure that allow unauthorized access or
  modification.
- Weaknesses in TLS, certificate validation, or client/server authentication
  that allow an attacker to impersonate a Landscape service, server, client, or
  administrator.

Landscape includes administrative features that intentionally perform powerful
operations. Arbitrary script execution on managed clients, for example, is an
intended administrator-controlled feature and is not a vulnerability by itself.
It is a security issue if an attacker can invoke it without the required
authorization, bypass its restrictions, or use it to gain access or privileges
that the feature is not intended to provide.

If you are unsure whether an issue is security-related, report it privately
rather than disclosing it publicly.

## Reporting a vulnerability

To report a security issue, file a [Private Security Report](https://github.com/Canonical/landscape-client/security/advisories/new)
or email [security@ubuntu.com](mailto:security@ubuntu.com) with a description of
the issue, the steps you took to create the issue, affected versions, and, if
known, mitigations for the issue.

The [Ubuntu Security disclosure and embargo policy](https://ubuntu.com/security/disclosure-policy)
contains more information about what you can expect when you contact us and what
we expect from you.

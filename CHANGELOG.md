# Changelog

Interfaces may change before 1.0; review release notes before upgrading a
consuming harness.

## 0.1.0

### Added

- Python 3.11–3.14 MCP adapter over the public async `etrade-python>=1.1,<2` APIs,
  with loopback Streamable HTTP and local stdio transports.
- Thirteen brokerage read tools, twenty general/specialized order previews, and
  local server status; shared placement, change placement, cancellation, and alert
  deletion tools available under independent, disabled-by-default permissions.
- Nine specialized order structures with complete replacement previews, full
  general-request fallbacks, exact decimal strings, and reusable placement inputs.
- Strict inputs, inlined discovery schemas, packaged field/tool guidance, native
  MCP error signaling, broker diagnostics, and bounded local validation details.
- Explicit environment/profile configuration, coordinated client credential
  storage, HTTP bearer/Host/Origin restrictions, tool allowlists, and opt-in
  redacted tool-call diagnostics on stderr.
- Direct, single-dispatch mutation wrappers with no implicit preview, execution
  state, automatic mutation retries, or server deduplication. Hosts own human
  approval, request binding, attempt history, and recovery after uncertain results.
- Offline real-client/mock-HTTP and actual MCP protocol tests; precision, multi-leg
  mapping, pagination, transport loss, process restart, and secret-handling checks.
- Four-worker test commands, Python-version CI, isolated wheel/sdist verification,
  and a release workflow for PyPI Trusted Publishing.
- Public Markdown documentation with MkDocs navigation/search, a concise README,
  and a GitHub Pages workflow separate from package publishing.

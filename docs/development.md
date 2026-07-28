# Development

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test,dev]'
```

## Quality gates

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy src
.venv/bin/python -m build
bash -n install.sh scripts/setup.sh scripts/terminal-ui.sh
git diff --check
```

## Design rules

- Keep dependencies pointing inward: presentation → application → domain; infrastructure implements ports; composition wires runtime objects.
- Keep prompts, filesystem writes, subprocesses, HTTP, and systemd in outer adapters.
- Use typed DTOs and explicit response validation for vendor contracts.
- Add tests before implementation for new behavior and include failure paths.
- Never expose secrets in `repr`, logs, exceptions, fixtures, or documentation.
- Verify both source behavior and package/installer artifacts.

## Documentation rules

`README.md` is intentionally short. Put operational procedures and architecture in `docs/`. Put observed web-console calls in one document per operation under `docs/web-console-api/`. Documentation describes the current implementation; do not add migration narratives or unverified compatibility claims.

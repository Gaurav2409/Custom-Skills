# BizX Repository Conventions

## Repo Types

| Type | Org | Naming | Example | Description |
|------|-----|--------|---------|-------------|
| BizX app | `bizx` | `au-*` | `bizx/au-servicecenter` | Application unit (monolith modules) |
| BizX platform | `bizx` | `idl-*` | `bizx/idl-sfbase` | Platform/shared libraries |
| Microservice | any org | `*-svc` | `sf-eas/eml-svc` | Standalone microservices |

## Search Tips

- `--owner bizx` searches all bizx repos
- `--repo` requires exact `owner/repo` — no wildcards
- Common orgs: `bizx`, `sf-eas`, `SFNext`

## Personal vs Org Repos

SAP personal repos use employee ID as owner (I-number, D-number, or C-number):

```python
# Skip personal repos in search results
owner = repo.split('/')[0]
if re.match(r'^[IDCidc]\d{5,}$', owner):
    continue
```

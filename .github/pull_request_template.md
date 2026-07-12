## Checklist

- [ ] I edited `projects.json`, not the generated `README.md`.
- [ ] I validated and sorted the project data.

```sh
uv run check-jsonschema --schemafile projects.schema.json projects.json
uv run scripts/sort_projects.py --check
```

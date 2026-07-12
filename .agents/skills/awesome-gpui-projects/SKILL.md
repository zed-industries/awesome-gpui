---
name: awesome-gpui-projects
description: Add or update projects in awesome-gpui, including categories, URLs, images, sorting, schema validation, and generated README checks. Use for any project-list maintenance in this repository.
---

# Awesome GPUI Projects

Edit `projects.json`; never include `README.md` changes in a pull request.

For each project:

- Use its canonical `https://` URL.
- GitHub URLs automatically receive stars and activity; other hosts show `N/A`.
- Choose a schema-defined `category`.
- Apps must have a schema-defined `subcategory`; other categories must not.
- `image` is optional and must be an HTTPS URL. Prefer a stable repository-hosted square icon over a screenshot or badge.
- Keep descriptions concise and preserve existing style.

Run, in order:

```sh
uv run check-jsonschema --schemafile projects.schema.json projects.json
uv run scripts/sort_projects.py
uv run scripts/sort_projects.py --check
uv run scripts/generate_readme.py
```

Review the generated `README.md` locally, confirm metadata changes are expected, then run `git restore README.md` before committing. The post-merge workflow updates it. Confirm sorting changed only placement and GitHub redirects use canonical URLs. Never commit `.env` or generated Python bytecode.

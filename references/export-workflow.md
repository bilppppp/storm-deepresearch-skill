# Export Workflow

`work/generations/g0001/artifacts/report.md` is the only authored public report. HTML and PDF are derivatives.

## Dependencies

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock
pandoc --version
```

Pinned Python dependencies are Jinja2, WeasyPrint, and pypdf. Pandoc is a system dependency. Chromium is the PDF fallback.

## Governed render stage

```bash
.venv/bin/python scripts/storm_research.py render "$RUN_DIR" \
  --template templates/report.html.j2
```

Pandoc creates the semantic HTML fragment. Jinja2 uses strict undefined variables to create the document. WeasyPrint renders PDF first; Chromium is attempted only when the preferred renderer fails. A successful render writes `60-render.json`.

## Reduced package

A reduced package may omit PDF only when the authoritative brief already has `output_mode: reduced`:

```bash
.venv/bin/python scripts/storm_research.py render "$RUN_DIR" \
  --template templates/report.html.j2 \
  --pdf-renderer none
```

Full dossiers cannot be amended from full to reduced after PDF failure. Fix the renderer or create a scoped non-release briefing.

## Render manifest

The exporter reads the generation artifact report and writes fixed generation `exports/` and `validation/` children. It rejects parent traversal and symlink escape. The render manifest records Markdown, HTML, PDF, and section fingerprints; validation fails when files drift, titles or sections diverge, template markers remain, or required PDF content is unavailable.

After validation passes, use `storm_research.py collect "$RUN_DIR" --to <new-dir>` for local handoff. It copies only report Markdown, HTML, PDF, and validation reports, verifies hashes, and does not create a public release package.

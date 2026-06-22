# Export Workflow

`report.md` is the only authored public report. HTML and PDF are derivatives.

## Dependencies

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock
pandoc --version
```

Pinned Python dependencies are Jinja2, WeasyPrint, and pypdf. Pandoc is a system dependency. Chromium is the PDF fallback.

## Full package

```bash
.venv/bin/python scripts/export_report.py "$RUN_DIR" \
  --template templates/report.html.j2 \
  --title "Research Report" \
  --require-pdf
```

Pandoc creates the semantic HTML fragment. Jinja2 uses strict undefined variables to create the document. WeasyPrint renders PDF first; Chromium is attempted only when the preferred renderer fails.

## Reduced package

A reduced package may omit PDF only when `brief.output_mode` is `reduced`:

```bash
.venv/bin/python scripts/export_report.py "$RUN_DIR" \
  --template templates/report.html.j2 \
  --title "Research Report" \
  --pdf-renderer none
```

## Render manifest

The exporter reads `$RUN_DIR/report.md` and writes fixed `exports/` and `validation/` children. It rejects parent traversal and symlink escape. The render manifest records Markdown, HTML, PDF, and section fingerprints; validation fails when files drift, titles or sections diverge, template markers remain, or required PDF content is unavailable.

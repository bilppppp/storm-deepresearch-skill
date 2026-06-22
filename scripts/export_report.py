#!/usr/bin/env python3
"""Render canonical Markdown to HTML and PDF with deterministic manifests."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.harness_io import atomic_write_json, atomic_write_text, sha256_file

try:
    from .output_paths import OutputPathError, package_child, resolve_package_dir
except ImportError:
    from output_paths import OutputPathError, package_child, resolve_package_dir


EXIT_ARGUMENT = 2
EXIT_DEPENDENCY = 3
EXIT_EXPORT = 6
EXIT_SAFETY = 7
DEFAULT_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


class RenderError(RuntimeError):
    """Raised when a required governed render artifact cannot be produced."""


@dataclass(frozen=True)
class RenderResult:
    html_path: Path
    pdf_path: Path | None
    manifest_path: Path
    pdf_renderer: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def markdown_sections(markdown: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current_title:
                normalized = " ".join("\n".join(current_lines).split())
                sections.append({"title": current_title, "sha256": sha256_bytes(normalized.encode("utf-8"))})
            current_title = line[3:].strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)
    if current_title:
        normalized = " ".join("\n".join(current_lines).split())
        sections.append({"title": current_title, "sha256": sha256_bytes(normalized.encode("utf-8"))})
    return sections


def pandoc_fragment(markdown_file: Path, pandoc: str) -> tuple[str, str]:
    binary = shutil.which(pandoc) if not Path(pandoc).is_absolute() else pandoc if Path(pandoc).is_file() else None
    if not binary:
        raise FileNotFoundError("Pandoc is unavailable")
    version = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise FileNotFoundError("Pandoc is unavailable")
    result = subprocess.run(
        [str(binary), str(markdown_file), "--from=gfm", "--to=html5", "--section-divs"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Pandoc failed: {result.stderr.strip()}")
    return result.stdout, version.stdout.splitlines()[0]


def toc_from_fragment(fragment: str) -> str:
    entries = []
    pattern = re.compile(
        r'<section id="([^"]+)" class="level2">\s*<h2>(.*?)</h2>',
        re.DOTALL,
    )
    for identifier, title_html in pattern.findall(fragment):
        title = re.sub(r"<[^>]+>", "", title_html)
        entries.append(f'<li><a href="#{html.escape(identifier, quote=True)}">{html.escape(title)}</a></li>')
    return '<nav aria-label="Table of contents"><h2>Contents</h2><ol>' + "".join(entries) + "</ol></nav>"


def render_template(template_path: Path, context: dict[str, object]) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
    except ImportError as exc:
        raise ModuleNotFoundError("Jinja2 is unavailable") from exc
    environment = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        autoescape=select_autoescape(("html", "xml")),
        keep_trailing_newline=True,
    )
    try:
        rendered = environment.get_template(template_path.name).render(**context)
    except Exception as exc:
        raise RuntimeError(f"template rendering failed: {exc}") from exc
    if re.search(r"(?:\{\{|\{%|\{#)", rendered):
        raise RuntimeError("template rendering failed: unresolved Jinja marker")
    return rendered


def render_pdf_weasyprint(html_path: Path, pdf_path: Path) -> None:
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise ModuleNotFoundError("WeasyPrint is unavailable") from exc
    HTML(filename=str(html_path), base_url=str(html_path.parent)).write_pdf(str(pdf_path))


def render_pdf_chromium(html_path: Path, pdf_path: Path, chrome: Path) -> None:
    if not chrome.is_file():
        raise FileNotFoundError("Chromium is unavailable")
    result = subprocess.run(
        [
            str(chrome), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri(),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"Chromium PDF rendering failed: {result.stderr.strip()}")


def create_pdf(html_path: Path, pdf_path: Path, renderer: str, chrome: Path) -> str:
    if renderer == "none":
        raise RuntimeError("PDF renderer is disabled")
    errors = []
    if renderer in {"auto", "weasyprint"}:
        try:
            render_pdf_weasyprint(html_path, pdf_path)
            return "weasyprint"
        except Exception as exc:
            errors.append(str(exc))
            if renderer == "weasyprint":
                raise RuntimeError("; ".join(errors)) from exc
    if renderer in {"auto", "chromium"}:
        try:
            render_pdf_chromium(html_path, pdf_path, chrome)
            return "chromium"
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) or "no PDF renderer available")


def markdown_title(markdown: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    if not match:
        raise RenderError("canonical Markdown is missing an H1 title")
    return match.group(1).strip()


def export_report(
    source_md: Path,
    staging_root: Path,
    *,
    title: str,
    template_path: Path,
    pandoc: str,
    chrome: Path,
    require_pdf: bool,
    pdf_renderer: str = "auto",
) -> RenderResult:
    if staging_root.exists() or staging_root.is_symlink():
        raise RenderError(f"render staging path already exists: {staging_root}")
    staging_root.mkdir(parents=True, exist_ok=False)
    exports = staging_root / "exports"
    validation = staging_root / "validation"
    exports.mkdir()
    validation.mkdir()
    markdown = source_md.read_text(encoding="utf-8")
    if markdown_title(markdown) != title:
        raise RenderError("render title does not match canonical Markdown H1")
    if "## References" not in markdown:
        raise RenderError("canonical Markdown is missing generated References")
    fragment, pandoc_version = pandoc_fragment(source_md, pandoc)
    generated_at = datetime.now(timezone.utc).isoformat()
    html_text = render_template(template_path, {
        "title": title,
        "body_html": fragment,
        "toc_html": toc_from_fragment(fragment),
        "generated_at": generated_at,
        "content_sha256": sha256_bytes(markdown.encode("utf-8")),
    })
    if f"<title>{html.escape(title)}</title>" not in html_text or "References" not in html_text:
        raise RenderError("Markdown and HTML title or References drift")
    html_path = exports / "report.html"
    atomic_write_text(html_path, html_text)
    pdf_path = exports / "report.pdf"
    renderer = "none"
    if require_pdf and pdf_renderer == "none":
        raise RenderError("required PDF cannot use the none renderer")
    if require_pdf or pdf_renderer != "none":
        try:
            renderer = create_pdf(html_path, pdf_path, pdf_renderer, chrome)
        except Exception as exc:
            raise RenderError(f"PDF rendering failed: {exc}") from exc
    page_count = 0
    if pdf_path.is_file():
        if not pdf_path.read_bytes().startswith(b"%PDF-"):
            raise RenderError("generated PDF is unreadable")
        try:
            page_count = len(PdfReader(pdf_path).pages)
        except Exception as exc:
            raise RenderError(f"generated PDF is unreadable: {exc}") from exc
        if page_count < 1:
            raise RenderError("generated PDF has no pages")
    if require_pdf and not pdf_path.is_file():
        raise RenderError("required PDF was not generated")
    manifest_path = validation / "render-manifest.json"
    atomic_write_json(manifest_path, {
        "schema_version": "2.0",
        "title": title,
        "generated_at": generated_at,
        "source_file": source_md.name,
        "report_md_sha256": sha256_file(source_md),
        "report_html_sha256": sha256_file(html_path),
        "report_pdf_sha256": sha256_file(pdf_path) if pdf_path.is_file() else None,
        "pandoc_version": pandoc_version,
        "pdf_renderer": renderer,
        "pdf_page_count": page_count,
        "section_fingerprints": markdown_sections(markdown),
    })
    return RenderResult(
        html_path=html_path,
        pdf_path=pdf_path if pdf_path.is_file() else None,
        manifest_path=manifest_path,
        pdf_renderer=renderer,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--template", type=Path, default=Path("templates/report.html.j2"))
    parser.add_argument("--title", required=True)
    parser.add_argument("--pandoc", default="pandoc")
    parser.add_argument("--pdf-renderer", choices=("auto", "weasyprint", "chromium", "none"), default="auto")
    parser.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    parser.add_argument("--require-pdf", action="store_true")
    args = parser.parse_args()

    try:
        package_dir = resolve_package_dir(args.package_dir)
        markdown_file = package_child(package_dir, "report.md")
        output_dir = package_child(package_dir, "exports")
        validation_dir = package_child(package_dir, "validation")
    except OutputPathError as exc:
        print(f"Unsafe research package path: {exc}", file=sys.stderr)
        return EXIT_SAFETY
    if not markdown_file.is_file() or not args.template.is_file():
        print("Markdown file or HTML template is missing.", file=sys.stderr)
        return EXIT_ARGUMENT
    if args.require_pdf and args.pdf_renderer == "none":
        print("A required PDF cannot be generated with the none renderer.", file=sys.stderr)
        return EXIT_EXPORT
    try:
        fragment, pandoc_version = pandoc_fragment(markdown_file, args.pandoc)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DEPENDENCY
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_EXPORT

    markdown_bytes = markdown_file.read_bytes()
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        document = render_template(args.template, {
            "title": args.title,
            "body_html": fragment,
            "toc_html": toc_from_fragment(fragment),
            "generated_at": generated_at,
            "content_sha256": sha256_bytes(markdown_bytes),
        })
    except ModuleNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DEPENDENCY
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_EXPORT

    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "report.html"
    pdf_path = output_dir / "report.pdf"
    html_path.write_text(document, encoding="utf-8")
    pdf_renderer = "none"
    if args.pdf_renderer != "none":
        try:
            pdf_renderer = create_pdf(html_path, pdf_path, args.pdf_renderer, args.chrome)
        except Exception as exc:
            if args.require_pdf:
                print(f"Failed to generate required PDF: {exc}", file=sys.stderr)
                return EXIT_EXPORT
            print(f"PDF not generated in reduced mode: {exc}", file=sys.stderr)
    if args.require_pdf and (not pdf_path.is_file() or not pdf_path.read_bytes().startswith(b"%PDF-")):
        print("Failed to generate required PDF.", file=sys.stderr)
        return EXIT_EXPORT

    validation_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "title": args.title,
        "generated_at": generated_at,
        "source_file": markdown_file.name,
        "report_md_sha256": sha256_bytes(markdown_bytes),
        "report_html_sha256": sha256_bytes(html_path.read_bytes()),
        "report_pdf_sha256": sha256_bytes(pdf_path.read_bytes()) if pdf_path.exists() else "",
        "pandoc_version": pandoc_version,
        "pdf_renderer": pdf_renderer,
        "section_fingerprints": markdown_sections(markdown_bytes.decode("utf-8")),
    }
    (validation_dir / "render-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {html_path}")
    if pdf_path.exists():
        print(f"Wrote {pdf_path} with {pdf_renderer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

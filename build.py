#!/usr/bin/env python3
"""
build.py - resume.md -> resume.html -> resume.pdf

Pipeline:  pandoc (md -> html)  ->  bs4 (structure/classes)  ->  CSS  ->  WeasyPrint

Usage:
    python3 build.py                      # resume.md -> resume.pdf
    python3 build.py -i other.md -o out.pdf
    python3 build.py --plain              # no [BRACKETS] around section headings
    python3 build.py --engine wkhtmltopdf # fallback engine (WeasyPrint is the default)
    python3 build.py --show-text          # also dump what a text extractor sees

Requires: pandoc, beautifulsoup4, weasyprint   (pip install beautifulsoup4 weasyprint)
Optional: poppler-utils (pdftotext/pdfinfo/pdffonts) for the post-build checks.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent

# Things a parser/recruiter must be able to find in the extracted PDF text.
EXPECTED_TEXT = [
    "Preston Crowe",
    "prestonjcrowe@protonmail.com",
    "EDUCATION",
    "EXPERIENCE",
    "SKILLS",
    "PUBLICATIONS",
    "ExtraHop",
    "University of Washington",
]


# --------------------------------------------------------------------------- #
# 1. markdown -> html (pandoc)
# --------------------------------------------------------------------------- #
def run_pandoc(md_path: Path) -> str:
    if not shutil.which("pandoc"):
        sys.exit("error: pandoc not found on PATH")
    # -smart: keep straight quotes (simpler for parsers); +lists_without_preceding_blankline: match GitHub-style lists
    cmd = ["pandoc", "-f", "markdown-smart+lists_without_preceding_blankline", "-t", "html5", "--wrap=none", str(md_path)]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


# --------------------------------------------------------------------------- #
# 2. structure the HTML so the CSS has something to hang decoration on
# --------------------------------------------------------------------------- #
def structure(fragment: str, css: str, plain: bool) -> str:
    frag = BeautifulSoup(fragment, "html.parser")

    h1 = frag.find("h1")
    name = h1.get_text(strip=True) if h1 else "Resume"

    # Wrap h1 + everything before the first h2 in <header>.
    first_h2 = frag.find("h2")
    header = frag.new_tag("header")
    for el in list(frag.children):
        if el is first_h2:
            break
        header.append(el.extract())

    # Section headings: optionally [BRACKETED]. Real text, so keep it sane.
    for h2 in frag.find_all("h2"):
        label = h2.get_text(strip=True)
        h2.string = label if plain else f"[{label}]"

    # Entry heads: a paragraph that *starts with* <strong> (company / school).
    # First one in each section gets .first (no dashed rule above it).
    seen_in_section = False
    for el in frag.children:
        if getattr(el, "name", None) == "h2":
            seen_in_section = False
        elif getattr(el, "name", None) == "p":
            first_child = next((c for c in el.children if getattr(c, "name", None) or str(c).strip()), None)
            if getattr(first_child, "name", None) == "strong":
                el["class"] = ["entry"] + ([] if seen_in_section else ["first"])
                seen_in_section = True

    # Skip-over leading text nodes whitespace; assemble the document.
    doc = BeautifulSoup(
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'></head><body></body></html>",
        "html.parser",
    )
    head, body = doc.head, doc.body
    t = doc.new_tag("title"); t.string = f"{name} - Resume"; head.append(t)
    for k, v in (("author", name), ("description", f"{name} - Security Engineer resume")):
        m = doc.new_tag("meta"); m["name"] = k; m["content"] = v; head.append(m)
    style = doc.new_tag("style"); style.string = css; head.append(style)
    body.append(header)
    for el in list(frag.children):
        body.append(el.extract())
    return str(doc)


# --------------------------------------------------------------------------- #
# 3. html -> pdf
# --------------------------------------------------------------------------- #
def render_weasyprint(html_path: Path, pdf_path: Path) -> None:
    try:
        from weasyprint import HTML
    except ImportError:
        sys.exit("error: weasyprint not installed (pip install weasyprint) "
                 "- or re-run with --engine wkhtmltopdf")
    HTML(filename=str(html_path), base_url=str(html_path.parent)).write_pdf(str(pdf_path))


def render_wkhtmltopdf(html_path: Path, pdf_path: Path, zoom: float) -> None:
    if not shutil.which("wkhtmltopdf"):
        sys.exit("error: wkhtmltopdf not found on PATH")
    # Unpatched-Qt wkhtmltopdf turns @font-face web fonts into vector outlines
    # (no text layer -> unparseable). Strip them and rely on the installed
    # "DejaVu Sans Mono" / "Liberation Mono" via the CSS fallback stack instead.
    tmp_html = html_path.with_name(html_path.stem + ".wk.html")
    tmp_html.write_text(
        re.sub(r"@font-face\s*\{[^}]*\}", "", html_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    cmd = [
        "wkhtmltopdf", "--quiet", "--enable-local-file-access", "--encoding", "utf-8",
        "--page-size", "Letter", "--print-media-type", "--disable-smart-shrinking",
        "--margin-top", "0.45in", "--margin-bottom", "0.45in",
        "--margin-left", "0.55in", "--margin-right", "0.55in",
        "--zoom", str(zoom),
        str(tmp_html), str(pdf_path),
    ]
    subprocess.run(cmd, check=True)
    tmp_html.unlink()


# --------------------------------------------------------------------------- #
# 4. sanity checks: what does a text extractor actually see?
# --------------------------------------------------------------------------- #
def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def verify(pdf_path: Path, show_text: bool) -> int:
    problems = 0
    print(f"\n== checks: {pdf_path.name} ==")

    if have("pdfinfo"):
        info = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True).stdout
        pages = re.search(r"Pages:\s+(\d+)", info)
        size = re.search(r"Page size:\s+(.+)", info)
        print(f"pages: {pages.group(1) if pages else '?'}    size: {size.group(1).strip() if size else '?'}")

    if have("pdffonts"):
        fonts = subprocess.run(["pdffonts", str(pdf_path)], capture_output=True, text=True).stdout
        rows = [r for r in fonts.splitlines()[2:] if r.strip()]
        # columns end with: emb sub uni objID gen  (type/encoding may contain spaces)
        not_embedded = []
        for r in rows:
            m = re.search(r"\s(yes|no)\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", r)
            if m and m.group(1) == "no":
                not_embedded.append(r.split()[0])
        print(f"fonts: {len(rows)} ({'all embedded' if not not_embedded else 'NOT embedded: ' + ', '.join(not_embedded)})")
        problems += bool(not_embedded)

    if have("pdftotext"):
        text = subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, text=True).stdout
        missing = [s for s in EXPECTED_TEXT if s.lower() not in text.lower()]
        print("expected strings:", "all found" if not missing else f"MISSING {missing}")
        problems += bool(missing)
        if "\ufffd" in text or re.search(r"[\ue000-\uf8ff]", text):
            print("glyph problem: replacement/private-use characters in extracted text")
            problems += 1
        if re.search(r"\b(?:[A-Za-z] ){5,}[A-Za-z]\b", text):
            print("spacing problem: looks like letter-spaced text (e.g. 'P R E S T O N')")
            problems += 1
        if show_text:
            print("\n---- extracted text (reading order) ----")
            print(text)
            print("---- end ----")

    try:
        from pypdf import PdfReader
        r = PdfReader(str(pdf_path))
        links = sum(
            1 for p in r.pages for a in (p.get("/Annots") or [])
            if a.get_object().get("/A", {}).get("/URI")
        )
        print(f"live hyperlinks: {links}")
    except Exception:
        pass

    print("result:", "OK" if not problems else f"{problems} problem(s)")
    return problems


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Build a styled, parser-friendly PDF resume from Markdown.")
    ap.add_argument("-i", "--input", default=str(HERE / "resume.md"))
    ap.add_argument("-o", "--output", default=str(HERE / "resume.pdf"))
    ap.add_argument("--css", default=str(HERE / "style.css"))
    ap.add_argument("--engine", choices=["weasyprint", "wkhtmltopdf"], default="weasyprint")
    ap.add_argument("--zoom", type=float, default=1.0, help="wkhtmltopdf only: page zoom factor")
    ap.add_argument("--plain", action="store_true", help="no [BRACKETS] around section headings")
    ap.add_argument("--no-check", action="store_true", help="skip post-build text-extraction checks")
    ap.add_argument("--show-text", action="store_true", help="print the text a parser would extract")
    args = ap.parse_args()

    md, out, css_path = Path(args.input), Path(args.output), Path(args.css)
    html_path = out.with_suffix(".html")

    fragment = run_pandoc(md)
    html = structure(fragment, css_path.read_text(encoding="utf-8"), args.plain)
    # The HTML sits next to fonts/ so the relative @font-face URLs resolve.
    html_path = HERE / (out.stem + ".html")
    html_path.write_text(html, encoding="utf-8")

    if args.engine == "weasyprint":
        render_weasyprint(html_path, out)
    else:
        render_wkhtmltopdf(html_path, out, args.zoom)
    print(f"built {out}  (engine: {args.engine})")

    if not args.no_check:
        sys.exit(1 if verify(out, args.show_text) else 0)


if __name__ == "__main__":
    main()

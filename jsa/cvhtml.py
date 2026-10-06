"""The CV as a typeset page, printed to PDF by a browser already on the machine.

`HtmlDocument` takes the same calls as `docx.Document`, so `build_cv` lays out
one CV and writes it in either format. The page is a single column of real
text in reading order — what a recruiter sees and what an ATS parses are the
same thing — and the browser's print engine does the typesetting.

No dependency: the PDF comes from Chrome, Edge or Chromium in headless mode.
When none is installed, `print_pdf` returns None and the .docx stands alone.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from .util import log

# A link-shaped token: an address, or a domain with a path.
EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
URL = re.compile(r"^(https?://)?([\w-]+\.)+[a-z]{2,}(/\S*)?$", re.I)
# What follows the dash in "MSc Politics — 102/110": a result, not an organisation.
GRADE = re.compile(r"\d+\s*/\s*\d+|cum laude|distinction|honou?rs|\bgpa\b|first class", re.I)

CSS = """
@page {
  size: A4;
  margin: 15mm 17mm 15mm 17mm;
  @bottom-right {
    content: "%(footer)s" counter(page) " / " counter(pages);
    font: 7pt/1 var(--font); color: #8792a2; letter-spacing: .04em;
  }
}
@page :first { @bottom-right { content: none; } }
:root {
  --font: "Helvetica Neue", Helvetica, Arial, "Liberation Sans", sans-serif;
  --ink: #16202b; --body: #2c3642; --muted: #5d6877; --rule: #cfd7e0;
  --accent: #1d5b74;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font: 9.3pt/1.4 var(--font); color: var(--body); background: #fff;
  font-kerning: normal; hyphens: manual;
  /* No ligatures: an ATS reads "ﬂ" as one unknown character, and "workﬂow"
     stops matching "workflow". */
  font-variant-ligatures: none; font-feature-settings: "liga" 0, "clig" 0, "dlig" 0;
}
a { color: inherit; text-decoration: none; }

header { padding-bottom: 9pt; margin-bottom: 2pt; border-bottom: 1.4pt solid var(--accent); }
h1 { font-size: 22pt; line-height: 1.05; font-weight: 700; letter-spacing: .035em; color: var(--ink); }
.headline {
  margin-top: 4pt; font-size: 8.6pt; font-weight: 600; letter-spacing: .16em;
  text-transform: uppercase; color: var(--accent);
}
.contact { margin-top: 5pt; font-size: 8.3pt; line-height: 1.5; color: var(--muted); }
.contact .sep { color: #b3bcc7; padding: 0 .45em; }

section { margin-top: 11pt; }
h2 {
  font-size: 8.2pt; font-weight: 700; letter-spacing: .17em; text-transform: uppercase;
  color: var(--accent); padding-bottom: 2.5pt; margin-bottom: 5pt;
  border-bottom: .6pt solid var(--rule); break-after: avoid;
}
p.body { text-align: left; }
p.note { font-size: 8.3pt; font-style: italic; color: var(--muted); margin-bottom: 4pt; }
p.line { margin-bottom: 2.2pt; }
p.line .label { font-weight: 700; color: var(--ink); }

.entry { margin-bottom: 6.5pt; break-inside: avoid; }
.entry:last-child { margin-bottom: 0; }
.head { display: flex; justify-content: space-between; align-items: baseline; gap: 12pt; }
.what { font-size: 9.6pt; color: var(--ink); }
.what strong { font-weight: 700; }
.what .org { font-weight: 600; color: var(--accent); }
.what .grade { font-weight: 400; color: var(--muted); }
.when { flex: none; font-size: 8.4pt; font-weight: 600; color: var(--muted);
        font-variant-numeric: tabular-nums; white-space: nowrap; }
.when.link { font-weight: 400; }
.meta { font-size: 8.3pt; font-style: italic; color: var(--muted); margin-top: .5pt; }

ul { list-style: none; margin-top: 2.5pt; }
li { position: relative; padding-left: 11pt; margin-bottom: 1.8pt; }
li::before {
  content: "•"; position: absolute; left: 1.5pt; top: 0;
  color: var(--accent); font-weight: 700;
}
"""


def _link(token: str) -> str:
    text = escape(token)
    if EMAIL.match(token):
        return f'<a href="mailto:{text}">{text}</a>'
    if URL.match(token) and ("/" in token or token.startswith("www.")):
        href = token if token.startswith("http") else f"https://{token}"
        return f'<a href="{escape(href)}">{escape(token.removeprefix("https://"))}</a>'
    return text


def _joined(text: str) -> str:
    """A ' · '-separated contact line, each part linked when it is a link."""
    return '<span class="sep">·</span>'.join(_link(part.strip()) for part in text.split(" · "))


@dataclass
class HtmlDocument:
    """Same interface as `docx.Document`; `save()` writes a print-ready page."""

    title: str = "Document"
    author: str = ""
    header: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    _contacts: int = 0
    _section: bool = False
    _entry: bool = False
    _list: bool = False

    # --------------------------------------------------------- structure

    def _close_list(self) -> None:
        if self._list:
            self.body.append("</ul>")
            self._list = False

    def _close_entry(self) -> None:
        self._close_list()
        if self._entry:
            self.body.append("</div>")
            self._entry = False

    def _close_section(self) -> None:
        self._close_entry()
        if self._section:
            self.body.append("</section>")
            self._section = False

    # ----------------------------------------------------------- content

    def name(self, text: str) -> None:
        self.header.append(f"<h1>{escape(text)}</h1>")

    def contact(self, text: str) -> None:
        # The first line under the name is the positioning; the rest is how to reach them.
        if not text:
            return
        if self._contacts == 0:
            self.header.append(f'<div class="headline">{escape(text)}</div>')
        else:
            self.header.append(f'<div class="contact">{_joined(text)}</div>')
        self._contacts += 1

    def section(self, text: str) -> None:
        self._close_section()
        self.body.append(f"<section><h2>{escape(text)}</h2>")
        self._section = True

    def paragraph(self, text: str, style: str = "Body") -> None:
        self._close_entry()
        if style == "Bullet":
            label, sep, rest = text.partition(": ")
            if sep and len(label) <= 40:
                self.body.append(
                    f'<p class="line"><span class="label">{escape(label)}:</span> {escape(rest)}</p>')
            else:
                self.body.append(f'<p class="line">{escape(text)}</p>')
        else:
            self.body.append(f'<p class="body">{escape(text)}</p>')

    def role(self, left: str, right: str = "") -> None:
        self._close_entry()
        title, sep, org = left.rpartition(" — ")
        kind = "grade" if GRADE.search(org) else "org"
        what = (f'<strong>{escape(title)}</strong><span class="{kind}"> — {escape(org)}</span>'
                if sep else f"<strong>{escape(left)}</strong>")
        when = ""
        if right:
            is_link = bool(URL.match(right)) and "/" in right
            cls = "when link" if is_link else "when"
            when = f'<span class="{cls}">{_link(right) if is_link else escape(right)}</span>'
        self.body.append(f'<div class="entry"><div class="head"><span class="what">{what}</span>{when}</div>')
        self._entry = True

    def meta(self, text: str) -> None:
        if not text:
            return
        cls = "meta" if self._entry else "note"
        self._close_list()
        tag = "div" if self._entry else "p"
        self.body.append(f'<{tag} class="{cls}">{escape(text)}</{tag}>')

    def bullet(self, text: str) -> None:
        if not self._list:
            self.body.append("<ul>")
            self._list = True
        self.body.append(f"<li>{escape(text)}</li>")

    def spacer(self, points: int = 6) -> None:
        self._close_entry()
        self.body.append(f'<div style="height:{points}pt"></div>')

    def page_break(self) -> None:
        self._close_entry()
        self.body.append('<div style="break-after:page"></div>')

    # -------------------------------------------------------------- save

    def html(self) -> str:
        self._close_section()
        footer = f"{self.author} · " if self.author else ""
        css = CSS % {"footer": footer.replace("\\", "\\\\").replace('"', '\\"')}
        return (
            '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f"<title>{escape(self.title)}</title>"
            f'<meta name="author" content="{escape(self.author)}">'
            f"<style>{css}</style></head><body>"
            f"<header>{''.join(self.header)}</header>"
            f"<main>{''.join(self.body)}</main></body></html>\n"
        )

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.html(), encoding="utf-8")
        return out


# ------------------------------------------------------------------ printing

def _candidates() -> list[str]:
    if sys.platform == "darwin":
        return [f"/Applications/{app}.app/Contents/MacOS/{app}" for app in
                ("Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser")]
    if os.name == "nt":
        roots = [os.environ.get(v, "") for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        tails = [r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"]
        return [str(Path(r) / t) for r in roots if r for t in tails]
    return [shutil.which(n) or "" for n in
            ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge")]


def find_browser() -> str | None:
    """A Chromium-based browser that can print headless, or None."""
    override = os.environ.get("JSA_BROWSER")
    if override:
        return override if Path(override).exists() else None
    return next((c for c in _candidates() if c and Path(c).exists()), None)


def print_pdf(html_path: str | Path, pdf_path: str | Path, *, timeout: int = 60) -> Path | None:
    """Print a local HTML page to PDF. None when no browser is available or it fails."""
    browser = find_browser()
    if not browser:
        return None
    src, out = Path(html_path).resolve(), Path(pdf_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    # A throwaway profile: never touches, or waits on, the person's open browser.
    with tempfile.TemporaryDirectory(prefix="jsa-print-") as profile:
        cmd = [browser, "--headless", "--disable-gpu", "--no-first-run",
               "--no-default-browser-check", "--disable-extensions",
               f"--user-data-dir={profile}", "--no-pdf-header-footer",
               "--print-to-pdf-no-header", f"--print-to-pdf={out}", src.as_uri()]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            log.warning("pdf: %s could not start (%s)", Path(browser).name, exc)
            return None
        # Headless Chrome on macOS can linger after writing the file, so wait
        # for the file to stop growing rather than for the process to exit.
        deadline, last = time.monotonic() + timeout, -1
        try:
            while time.monotonic() < deadline:
                if proc.poll() is not None and not out.exists():
                    break
                size = out.stat().st_size if out.exists() else -1
                if size > 0 and size == last:
                    break
                last = size
                time.sleep(0.4)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
    if not out.exists() or out.stat().st_size == 0:
        log.warning("pdf: %s produced no file", Path(browser).name)
        return None
    return out

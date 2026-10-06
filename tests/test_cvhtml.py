import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsa import cvhtml
from jsa.util import read_json
from jsa.cvhtml import HtmlDocument, find_browser, print_pdf
from jsa.docx import extract_text
from jsa.render import Overlay, build_cv, build_cv_pdf

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profile.example" / "profile.json"
TRACKS = ROOT / "profile.example" / "tracks.json"


def visible(html: str) -> str:
    """The page's text as a reader sees it: tags out, entities back."""
    from html import unescape

    body = html.split("<body>", 1)[1]
    return unescape(re.sub(r"<[^>]+>", " ", body))


class TestHtmlDocument(unittest.TestCase):
    def test_text_is_escaped(self):
        doc = HtmlDocument(title="CV", author="A")
        doc.section("Skills")
        doc.paragraph("Tools: <script>alert(1)</script> & more", style="Bullet")
        html = doc.html()
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_contact_lines_link_email_and_profiles(self):
        doc = HtmlDocument()
        doc.name("ANA KOWALSKA")
        doc.contact("Data & Operations")
        doc.contact("+48 600 000 000 · ana@example.com · linkedin.com/in/ana · github.com/ana")
        html = doc.html()
        self.assertIn('class="headline">Data &amp; Operations', html)
        self.assertIn('href="mailto:ana@example.com"', html)
        self.assertIn('href="https://linkedin.com/in/ana"', html)
        self.assertIn('href="https://github.com/ana"', html)
        self.assertNotIn('href="+48', html)

    def test_a_grade_is_not_styled_as_an_employer(self):
        doc = HtmlDocument()
        doc.section("Education")
        doc.role("MSc Economics — 110/110 cum laude", "2025")
        doc.section("Experience")
        doc.role("Analyst — Acme", "2024 – 2025")
        html = doc.html()
        self.assertIn('class="grade"> — 110/110', html)
        self.assertIn('class="org"> — Acme', html)

    def test_entries_wrap_their_bullets_so_a_role_never_splits_across_pages(self):
        doc = HtmlDocument()
        doc.section("Experience")
        doc.role("Analyst — Acme", "2024")
        doc.meta("Kraków")
        doc.bullet("One")
        doc.bullet("Two")
        doc.role("Intern — Beta", "2023")
        doc.bullet("Three")
        html = doc.html()
        first = html[html.index('<div class="entry">'):html.index("Intern")]
        self.assertEqual(first.count("<li>"), 2)
        self.assertEqual(html.count("<ul>"), html.count("</ul>"))
        self.assertEqual(html.count('<div class="entry">') + html.count('<div class="head">')
                         + html.count('<div class="meta">'), html.count("</div>"))

    def test_no_ligatures_reach_the_pdf(self):
        # "ﬂ" is one glyph to an ATS: "workﬂow" would stop matching "workflow".
        self.assertIn("font-variant-ligatures: none", HtmlDocument().html())


class TestSameCvBothFormats(unittest.TestCase):
    def test_html_and_docx_carry_the_same_words(self):
        profile, tracks = read_json(PROFILE), read_json(TRACKS)["tracks"]
        with TemporaryDirectory() as tmp:
            docx = build_cv(profile, tracks[0], overlay=Overlay(), path=Path(tmp) / "cv.docx")
            html = build_cv(profile, tracks[0], overlay=Overlay(), path=Path(tmp) / "cv.html")
            words = lambda t: re.findall(r"[\w%+/.-]+", t.replace("•", ""))
            self.assertEqual(sorted(words(extract_text(docx))),
                             sorted(words(visible(html.read_text()))))


class TestPrinting(unittest.TestCase):
    def test_no_browser_means_no_pdf_and_no_error(self):
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"JSA_BROWSER": "none"}):
            self.assertIsNone(find_browser())
            page = Path(tmp) / "p.html"
            page.write_text("<p>x</p>")
            self.assertIsNone(print_pdf(page, Path(tmp) / "p.pdf"))
            profile, tracks = read_json(PROFILE), read_json(TRACKS)["tracks"]
            self.assertIsNone(build_cv_pdf(profile, tracks[0], path=Path(tmp) / "cv.pdf"))

    def test_a_browser_that_writes_nothing_is_reported_not_trusted(self):
        with TemporaryDirectory() as tmp:
            fake = Path(tmp) / "browser"
            fake.write_text("")
            page = Path(tmp) / "p.html"
            page.write_text("<p>x</p>")
            done = mock.Mock(poll=mock.Mock(return_value=0))
            with mock.patch.dict(os.environ, {"JSA_BROWSER": str(fake)}), \
                    mock.patch.object(cvhtml.subprocess, "Popen", return_value=done):
                self.assertIsNone(print_pdf(page, Path(tmp) / "p.pdf"))


if __name__ == "__main__":
    unittest.main()

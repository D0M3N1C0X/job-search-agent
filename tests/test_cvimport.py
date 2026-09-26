"""Reading a CV that somebody else wrote.

A CV has no schema. These tests pin the shapes the parser claims to handle and,
just as importantly, the cases where it must refuse rather than guess.
"""

import unittest
import zipfile
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsa.cvimport import UnreadableCV, Draft, parse, read_text, to_profile, _heading
from jsa import pdftext
from jsa.pdftext import extract, legibility
from jsa.util import read_json

EXAMPLE = Path(__file__).resolve().parent.parent / "profile.example" / "profile.json"

ENGLISH = """ALEX RIVERA
HR Operations | People Analytics
Amsterdam, Netherlands · EU Citizen
+31 6 12345678 · alex@example.com
linkedin.com/in/alexrivera · github.com/alexrivera

PROFILE
HR operations specialist working across three European entities.

CORE SKILLS
Employee Relations · HR Policy · Case Management · Python · SQL

PROFESSIONAL EXPERIENCE
HR Operations Specialist — Example CorpJan 2024 – Present
Example Corp · Amsterdam (Hybrid)
Resolved around 120 HR cases per week across three European entities.
Turned recurring case patterns into process changes.

HR AssistantSep 2022 – Dec 2023
Sample Group · Rotterdam
Supported onboarding for around 300 employees.

EDUCATION
MSc Human Resource Management — 110/1102022
Example University · Coursework: Labour Law

LANGUAGES & CERTIFICATIONS
English (C1) · Dutch (B1) · Spanish (native)
People Analytics — Some University, 2024
"""

ITALIAN = """GIULIA BIANCHI
Specialista Risorse Umane
Milano, Italia
+39 333 1234567 · giulia@example.com

PROFILO
Specialista HR con esperienza in amministrazione del personale.

COMPETENZE
Amministrazione del personale · Relazioni sindacali · Excel

ESPERIENZA PROFESSIONALE
HR SpecialistGen 2023 – Presente
Esempio SpA · Milano
Gestione di 150 pratiche al mese.

FORMAZIONE
Laurea Magistrale in Economia2021
Università di Bologna

LINGUE
Italiano (madrelingua) · Inglese (B2)
"""


class TestHeadings(unittest.TestCase):
    def test_english_and_italian_headings_are_both_recognised(self):
        self.assertEqual(_heading("PROFESSIONAL EXPERIENCE"), "experience")
        self.assertEqual(_heading("Esperienza professionale"), "experience")
        self.assertEqual(_heading("FORMAZIONE"), "education")
        self.assertEqual(_heading("Lingue"), "languages")

    def test_letter_spaced_headings_are_recognised(self):
        # Designers letter-space headings and a PDF preserves it faithfully.
        self.assertEqual(_heading("P R O F E S S I O N A L  E X P E R I E N C E"), "experience")
        self.assertEqual(_heading("E D U C A T I O N"), "education")

    def test_ordinary_sentences_are_not_headings(self):
        self.assertIsNone(_heading("Resolved around 120 HR cases per week."))
        self.assertIsNone(_heading("Example Corp · Amsterdam"))


class TestParsingEnglish(unittest.TestCase):
    def setUp(self):
        self.draft = parse(ENGLISH, "text")

    def test_identity(self):
        self.assertEqual(self.draft.name, "ALEX RIVERA")
        self.assertEqual(self.draft.email, "alex@example.com")
        self.assertEqual(self.draft.phone, "+31 6 12345678")
        self.assertEqual(self.draft.linkedin, "linkedin.com/in/alexrivera")
        self.assertEqual(self.draft.github, "github.com/alexrivera")
        self.assertEqual(self.draft.country, "NL")

    def test_experience_roles_and_bullets(self):
        self.assertEqual(len(self.draft.experience), 2)
        first = self.draft.experience[0]
        self.assertIn("HR Operations Specialist", first["title"])
        self.assertEqual(first["start"], "Jan 2024")
        self.assertEqual(first["end"], "Present")
        self.assertEqual(first["company"], "Example Corp")
        self.assertEqual(len(first["bullets"]), 2)

    def test_languages_with_levels(self):
        levels = {l["name"]: l["level"] for l in self.draft.languages}
        self.assertEqual(levels.get("English"), "C1")
        self.assertEqual(levels.get("Spanish"), "native")

    def test_skills_are_split_on_separators(self):
        self.assertIn("Employee Relations", self.draft.skills)
        self.assertIn("Python", self.draft.skills)

    def test_nothing_is_reported_missing(self):
        self.assertEqual(self.draft.missing, [])


class TestParsingItalian(unittest.TestCase):
    def test_an_italian_cv_parses_too(self):
        draft = parse(ITALIAN, "text")
        self.assertEqual(draft.name, "GIULIA BIANCHI")
        self.assertEqual(draft.country, "IT")
        self.assertEqual(len(draft.experience), 1)
        self.assertEqual(draft.experience[0]["end"], "Presente")
        levels = {l["name"]: l["level"] for l in draft.languages}
        self.assertEqual(levels.get("Italiano"), "native")   # madrelingua
        self.assertEqual(levels.get("Inglese"), "B2")


class TestRefusals(unittest.TestCase):
    def test_a_missing_file_is_refused_clearly(self):
        with self.assertRaises(UnreadableCV) as caught:
            read_text("/nowhere/cv.docx")
        self.assertIn("does not exist", str(caught.exception))

    def test_an_unsupported_format_names_what_is_supported(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cv.odt"
            path.write_text("x" * 500)
            with self.assertRaises(UnreadableCV) as caught:
                read_text(path)
        self.assertIn(".docx", str(caught.exception))

    def test_an_almost_empty_file_is_refused(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cv.txt"
            path.write_text("Alex Rivera")
            with self.assertRaises(UnreadableCV):
                read_text(path)

    def test_an_old_doc_renamed_to_docx_is_refused_without_a_traceback(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cv.docx"
            path.write_bytes(b"\xd0\xcf\x11\xe0" + b"\0" * 600)   # the OLE header of a .doc
            with self.assertRaises(UnreadableCV) as caught:
                read_text(path)
        self.assertIn("not a readable .docx", str(caught.exception))

    def test_a_docx_that_inflates_to_gigabytes_is_refused_before_it_does(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cv.docx"
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("word/document.xml", "<w:p>" + "x" * 5000 + "</w:p>")
            with mock.patch("jsa.docx.MAX_DOCUMENT_XML", 1000):
                with self.assertRaises(UnreadableCV):
                    read_text(path)


class TestToProfile(unittest.TestCase):
    def test_the_draft_fills_the_example_shape(self):
        profile = to_profile(parse(ENGLISH, "text"), read_json(EXAMPLE))
        self.assertEqual(profile["identity"]["name"], "ALEX RIVERA")
        self.assertEqual(profile["identity"]["email"], "alex@example.com")
        self.assertEqual(len(profile["experience"]), 2)
        self.assertIn("preferences", profile)          # defaults survive
        self.assertIn("NL", profile["preferences"]["countries_allowed"])

    def test_an_empty_draft_leaves_the_example_untouched(self):
        base = read_json(EXAMPLE)
        profile = to_profile(Draft(), base)
        self.assertEqual(profile["identity"]["name"], base["identity"]["name"])


def minimal_pdf(text: str, compress: bool) -> bytes:
    """A hand-built PDF with one uncompressed or deflated content stream."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    if compress:
        stream, filt = zlib.compress(content), b"/Filter /FlateDecode "
    else:
        stream, filt = content, b""
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<<" + filt + b"/Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = b"%PDF-1.4\n"
    for i, body in enumerate(objs, 1):
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    return out + b"trailer<</Root 1 0 R>>\n%%EOF"


class TestPdfText(unittest.TestCase):
    def read(self, compress: bool) -> str:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.pdf"
            path.write_bytes(minimal_pdf("Hello world", compress))
            return extract(path)

    def test_a_deflated_stream_is_read(self):
        self.assertIn("Hello world", self.read(compress=True))

    def test_a_stream_with_no_filter_is_read(self):
        # Declaring no /Filter means the bytes are already plain; inflating
        # them anyway silently loses the whole page.
        self.assertIn("Hello world", self.read(compress=False))

    def test_a_stream_that_inflates_past_any_cv_is_dropped(self):
        with mock.patch.object(pdftext, "MAX_STREAM", 1000):
            self.assertIsNone(pdftext._inflate(zlib.compress(b"\0" * 50_000)))
            self.assertEqual(pdftext._inflate(zlib.compress(b"short")), b"short")

    def test_legibility_separates_prose_from_rubbish(self):
        self.assertGreater(legibility("Employee relations and HR policy, 2026."), 0.95)
        self.assertLess(legibility("\x01\x9a\xffÍÑkpãº9A&^>n#?QY>kDMý"), 0.6)
        self.assertEqual(legibility(""), 0.0)


if __name__ == "__main__":
    unittest.main()

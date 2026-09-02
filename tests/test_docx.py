import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.docx import Document, extract_text


class TestDocx(unittest.TestCase):
    def build(self, tmp: str) -> Path:
        doc = Document(title="CV", author="Alex Rivera")
        doc.name("ALEX RIVERA")
        doc.contact("Amsterdam · alex@example.com · +31 6 0000 0000")
        doc.section("Experience")
        doc.role("HR Advisor — Acme & Co", "Jan 2024 – Present")
        doc.meta("Amsterdam (Hybrid)")
        doc.bullet('Handled <120> cases per week & kept "quality" high.')
        return doc.save(Path(tmp) / "cv.docx")

    def test_produces_a_valid_openxml_package(self):
        with TemporaryDirectory() as tmp:
            path = self.build(tmp)
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                self.assertEqual(z.testzip(), None)
            for part in ("[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"):
                self.assertIn(part, names)

    def test_roundtrips_text_including_escaped_characters(self):
        with TemporaryDirectory() as tmp:
            text = extract_text(self.build(tmp))
            self.assertIn("ALEX RIVERA", text)
            self.assertIn("Acme & Co", text)
            self.assertIn('<120>', text)
            self.assertIn('"quality"', text)

    def test_name_is_the_first_line_for_ats_reading_order(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(extract_text(self.build(tmp)).split("\n")[0], "ALEX RIVERA")

    def test_no_tables_or_text_boxes_in_the_markup(self):
        doc = Document()
        doc.section("X")
        doc.bullet("y")
        xml = doc.document_xml()
        for hostile in ("<w:tbl>", "<w:txbxContent>", "<w:hdr>", "<w:ftr>"):
            self.assertNotIn(hostile, xml)


if __name__ == "__main__":
    unittest.main()

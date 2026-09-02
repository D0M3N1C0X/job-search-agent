"""A .docx writer built on the standard library.

A .docx is a ZIP of XML parts, so `zipfile` plus careful string building is
all it takes — no python-docx, no LaTeX, no fonts to install, nothing to pip
install before the repo runs.

The output is deliberately boring: one column, no tables, no text boxes, no
headers or footers, literal bullet characters. That is what survives an
applicant tracking system's text extraction intact.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

# A4 in twips (1/1440 inch), with 0.75" margins.
PAGE_W, PAGE_H = 11906, 16838
MARGIN = 1080
RIGHT_TAB = PAGE_W - 2 * MARGIN

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _style(style_id: str, name: str, *, size: int, bold: bool = False, caps: bool = False,
           color: str = "000000", space_before: int = 0, space_after: int = 0,
           border: bool = False, default: bool = False) -> str:
    """One paragraph style. `size` is in points."""
    ppr = [f'<w:spacing w:before="{space_before}" w:after="{space_after}" w:line="240" w:lineRule="auto"/>']
    if border:
        ppr.append('<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="9AA0A6"/></w:pBdr>')
    rpr = [f'<w:sz w:val="{size * 2}"/><w:szCs w:val="{size * 2}"/>', f'<w:color w:val="{color}"/>']
    if bold:
        rpr.append("<w:b/>")
    if caps:
        rpr.append("<w:caps/><w:spacing w:val=\"20\"/>")
    flag = ' w:default="1"' if default else ""
    return (
        f'<w:style w:type="paragraph"{flag} w:styleId="{style_id}">'
        f'<w:name w:val="{name}"/><w:qFormat/>'
        f'<w:pPr>{"".join(ppr)}</w:pPr><w:rPr>{"".join(rpr)}</w:rPr></w:style>'
    )


def styles_xml(font: str = "Calibri", base_size: int = 10) -> str:
    styles = "".join([
        _style("Normal", "Normal", size=base_size, space_after=40, default=True),
        _style("Name", "Name", size=20, bold=True, space_after=20),
        _style("Contact", "Contact", size=base_size - 1, color="444444", space_after=20),
        _style("Section", "Section Heading", size=base_size + 1, bold=True, caps=True,
               color="1A1A1A", space_before=180, space_after=60, border=True),
        _style("RoleLine", "Role Line", size=base_size, bold=True, space_before=80, space_after=0),
        _style("MetaLine", "Meta Line", size=base_size - 1, color="444444", space_after=40),
        _style("Bullet", "Bullet", size=base_size, space_after=30),
        _style("Body", "Body", size=base_size, space_after=100),
    ])
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>
<w:sz w:val="{base_size * 2}"/><w:szCs w:val="{base_size * 2}"/>
<w:lang w:val="en-GB"/></w:rPr></w:rPrDefault></w:docDefaults>
{styles}</w:styles>"""


CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>{title}</dc:title><dc:creator>{author}</dc:creator>
<cp:lastModifiedBy>{author}</cp:lastModifiedBy></cp:coreProperties>"""


@dataclass
class Document:
    """Build a document paragraph by paragraph, then `save()`."""

    title: str = "Document"
    author: str = ""
    font: str = "Calibri"
    base_size: int = 10
    body: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- runs

    @staticmethod
    def _run(text: str, *, bold: bool = False, italic: bool = False,
             size: int | None = None, color: str | None = None) -> str:
        props = []
        if bold:
            props.append("<w:b/>")
        if italic:
            props.append("<w:i/>")
        if size:
            props.append(f'<w:sz w:val="{size * 2}"/>')
        if color:
            props.append(f'<w:color w:val="{color}"/>')
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

    def _p(self, style: str, runs: str, *, extra_ppr: str = "") -> None:
        self.body.append(f'<w:p><w:pPr><w:pStyle w:val="{style}"/>{extra_ppr}</w:pPr>{runs}</w:p>')

    # ---------------------------------------------------------- content

    def name(self, text: str) -> None:
        self._p("Name", self._run(text))

    def contact(self, text: str) -> None:
        self._p("Contact", self._run(text))

    def section(self, text: str) -> None:
        self._p("Section", self._run(text))

    def paragraph(self, text: str, style: str = "Body") -> None:
        self._p(style, self._run(text))

    def role(self, left: str, right: str = "") -> None:
        """Bold role title on the left, dates flush right on the same line."""
        tabs = f'<w:tabs><w:tab w:val="right" w:pos="{RIGHT_TAB}"/></w:tabs>'
        runs = self._run(left, bold=True)
        if right:
            runs += f"<w:r><w:tab/></w:r>" + self._run(right, bold=False, color="444444")
        self._p("RoleLine", runs, extra_ppr=tabs)

    def meta(self, text: str) -> None:
        self._p("MetaLine", self._run(text, italic=True))

    def bullet(self, text: str) -> None:
        indent = '<w:ind w:left="284" w:hanging="284"/>'
        self._p("Bullet", self._run(f"•\t{text}"), extra_ppr=indent)

    def spacer(self, points: int = 6) -> None:
        self.body.append(
            f'<w:p><w:pPr><w:spacing w:after="{points * 20}"/></w:pPr></w:p>'
        )

    def page_break(self) -> None:
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    # ------------------------------------------------------------- save

    def document_xml(self) -> str:
        section = (
            f'<w:sectPr><w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}"/>'
            f'<w:pgMar w:top="{MARGIN}" w:right="{MARGIN}" w:bottom="{MARGIN}" '
            f'w:left="{MARGIN}" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{''.join(self.body)}{section}</w:body></w:document>"
        )

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", RELS)
            z.writestr("word/_rels/document.xml.rels", DOC_RELS)
            z.writestr("word/styles.xml", styles_xml(self.font, self.base_size))
            z.writestr("word/document.xml", self.document_xml())
            z.writestr(
                "docProps/core.xml",
                CORE.format(title=escape(self.title), author=escape(self.author)),
            )
        return out

    def plain_text(self) -> str:
        """The text an ATS would extract. Used by the built-in ATS check."""
        import re

        xml = self.document_xml()
        xml = xml.replace("</w:p>", "\n").replace("<w:tab/>", "\t")
        text = re.sub(r"<[^>]+>", "", xml)
        return "\n".join(line.strip() for line in text.split("\n")).strip()


def extract_text(path: str | Path) -> str:
    """Read a .docx back as plain text — no dependency, works on any .docx."""
    import re

    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    xml = xml.replace("</w:p>", "\n").replace("<w:tab/>", "\t").replace("<w:br/>", "\n")
    text = re.sub(r"<[^>]+>", "", xml)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(entity, char)
    return "\n".join(line.strip() for line in text.split("\n")).strip()

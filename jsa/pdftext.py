"""Text out of a PDF, with the standard library only.

A PDF does not store text; it stores glyph codes plus instructions for
drawing them. When the fonts are subset — which is what Word, Pages and
LaTeX all produce — those codes mean nothing on their own: code 3 might be
"a" in one font and "e" in the next. Reading the parenthesised strings
directly, which is the usual quick trick, therefore returns gibberish.

What makes it recoverable is the /ToUnicode CMap most producers embed
alongside each font precisely so that copy-paste works. This module finds
those maps, tracks which font is selected when each string is drawn, and
translates. Where there is no map it falls back to the raw bytes and says so,
because a confident wrong answer is worse than an admitted failure.
"""

from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path

# object 12 0 obj ... endobj
_OBJ = re.compile(rb"(\d+)\s+\d+\s+obj\b(.*?)\bendobj", re.S)
# Some writers put no newline before endstream, so do not require one.
_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
_FILTER = re.compile(rb"/Filter\s*(?:\[([^\]]*)\]|/([A-Za-z0-9]+))")
_TOUNICODE = re.compile(rb"/ToUnicode\s+(\d+)\s+\d+\s+R")
# The page resource dictionary: /Font << /F1 12 0 R /F2 13 0 R >>. Matching
# "/name n 0 R" anywhere instead picks up the font's own keys (/ToUnicode,
# /FontFile2) and maps nothing usable.
_FONT_INLINE = re.compile(rb"/Font\s*<<(.*?)>>", re.S)
_FONT_REF = re.compile(rb"/Font\s+(\d+)\s+\d+\s+R")
_FONT_RES = re.compile(rb"/([A-Za-z0-9#+.-]+)\s+(\d+)\s+\d+\s+R")
_BFCHAR = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
_BFRANGE = re.compile(rb"beginbfrange(.*?)endbfrange", re.S)
_HEX = re.compile(rb"<([0-9A-Fa-f]+)>")
# Content-stream operators we care about: font selection and text showing.
# A PDF has no lines. Text is drawn at coordinates, so where the page shows a
# line break the file shows only a cursor move. Without tracking those moves an
# entire CV comes out as one unbroken string, which no parser can segment.
_OPS = re.compile(
    rb"/(?P<font>[A-Za-z0-9#+.-]+)\s+[\d.]+\s+Tf"
    rb"|(?P<x>-?[\d.]+)\s+(?P<y>-?[\d.]+)\s+T[dD]"
    rb"|(?:-?[\d.]+\s+){5}(?P<my>-?[\d.]+)\s+Tm"
    rb"|(?P<star>T\*)"
    rb"|(?P<array>\[.*?\]\s*T[Jj])"
    rb"|(?P<single>(?:\(.*?\)|<[0-9A-Fa-f\s]*>)\s*T[Jj])",
    re.S,
)
# Text can be written as a literal (abc) or as hex <616263>. Producers that
# subset their fonts almost always use hex, which is why reading only the
# parenthesised form returns nothing at all from a Word export.
_STRING = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>", re.S)

_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
            b"(": b"(", b")": b")", b"\\": b"\\"}


def _unescape(raw: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(raw):
        if raw[i:i + 1] == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            if nxt in _ESCAPES:
                out += _ESCAPES[nxt]
                i += 2
                continue
            if nxt.isdigit():  # octal \053
                digits = raw[i + 1:i + 4]
                octal = bytes(c for c in digits if 0x30 <= c <= 0x37)
                if octal:
                    out.append(int(octal, 8) & 0xFF)
                    i += 1 + len(octal)
                    continue
            out += nxt
            i += 2
            continue
        out += raw[i:i + 1]
        i += 1
    return bytes(out)


# A CV's content streams are kilobytes. One that inflates past this is not a
# CV, and inflating it anyway is how a small file fills the memory.
MAX_STREAM = 16 * 1024 * 1024


def _inflate(data: bytes) -> bytes | None:
    # A decompressobj tolerates the truncated streams and trailing bytes some
    # exporters write; raw deflate (-15) covers streams with no zlib header.
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        inflater = zlib.decompressobj(wbits)
        try:
            out = inflater.decompress(data, MAX_STREAM)
        except zlib.error:
            continue
        return None if inflater.unconsumed_tail else out
    return None


def _decompress(body: bytes) -> bytes | None:
    """Undo the stream's filter chain.

    Filters are applied in order and there is often more than one: ReportLab
    writes [/ASCII85Decode /FlateDecode], and inflating without un-ASCII85-ing
    first fails on every page of the document.
    """
    match = _STREAM.search(body)
    if not match:
        return None
    data = match.group(1).strip(b"\r\n")

    found = _FILTER.search(body)
    if not found:
        return data  # no filter declared: the stream is already plain
    names = re.findall(rb"/([A-Za-z0-9]+)", found.group(1) or found.group(2) or b"")
    if not names:
        names = [b"FlateDecode"]

    for name in names:
        if name in (b"FlateDecode", b"Fl"):
            data = _inflate(data)
        elif name in (b"ASCII85Decode", b"A85"):
            try:
                data = base64.a85decode(data, adobe=True)
            except ValueError:
                return None
        elif name in (b"ASCIIHexDecode", b"AHx"):
            digits = re.sub(rb"[^0-9A-Fa-f]", b"", data.split(b">")[0])
            data = bytes.fromhex(digits.decode()) if digits else None
        elif name in (b"DCTDecode", b"JPXDecode", b"CCITTFaxDecode", b"JBIG2Decode"):
            return None  # an image, nothing to read here
        if data is None:
            return None
    return data


def _parse_cmap(data: bytes) -> dict[int, str]:
    """Turn a /ToUnicode CMap into {glyph code: text}."""
    mapping: dict[int, str] = {}

    def to_text(hex_bytes: str) -> str:
        raw = bytes.fromhex(hex_bytes)
        try:  # CMap targets are UTF-16BE
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            return raw.decode("latin-1", "ignore")

    for block in _BFCHAR.findall(data):
        items = _HEX.findall(block)
        for src, dst in zip(items[0::2], items[1::2]):
            mapping[int(src, 16)] = to_text(dst.decode())

    for block in _BFRANGE.findall(data):
        # <lo> <hi> <dst>  — destinations may also be an array, which we skip
        for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
                                      block):
            start, end = int(lo, 16), int(hi, 16)
            base = to_text(dst.decode())
            if not base or end - start > 0xFFFF:
                continue
            for offset in range(end - start + 1):
                mapping[start + offset] = base[:-1] + chr(ord(base[-1]) + offset)
    return mapping


def _decode(raw: bytes, cmap: dict[int, str] | None, two_byte: bool) -> str:
    if not cmap:
        return raw.decode("latin-1", "ignore")
    out = []
    if two_byte:
        for i in range(0, len(raw) - 1, 2):
            out.append(cmap.get((raw[i] << 8) | raw[i + 1], ""))
    else:
        for byte in raw:
            out.append(cmap.get(byte, ""))
    return "".join(out)


def extract(path: str | Path) -> str:
    """Best-effort plain text. Returns "" when nothing legible comes out."""
    raw = Path(path).read_bytes()
    objects = {int(num): body for num, body in _OBJ.findall(raw)}

    # Every font object that carries a /ToUnicode map.
    cmaps: dict[int, dict[int, str]] = {}
    for num, body in objects.items():
        ref = _TOUNICODE.search(body)
        if not ref:
            continue
        target = objects.get(int(ref.group(1)))
        data = _decompress(target) if target else None
        if data:
            cmaps[num] = _parse_cmap(data)

    # Resource name (/F1) -> font object, gathered across the whole file. Page
    # resources are per-page, but names are consistent enough in practice and a
    # wrong guess degrades to the raw bytes rather than to nonsense.
    names: dict[bytes, int] = {}
    blocks: list[bytes] = []
    for body in objects.values():
        blocks += _FONT_INLINE.findall(body)
        # /Font may also point at a separate dictionary object.
        for ref in _FONT_REF.findall(body):
            target = objects.get(int(ref))
            if target:
                blocks.append(target)
    for block in blocks:
        for name, target in _FONT_RES.findall(block):
            if int(target) in cmaps:
                names[name] = int(target)

    pieces: list[str] = []
    for body in objects.values():
        content = _decompress(body)
        if not content or (b"Tj" not in content and b"TJ" not in content):
            continue
        current: dict[int, str] | None = None
        two_byte = False
        last_y: float | None = None
        for match in _OPS.finditer(content):
            group = match.groupdict()
            if group["font"] is not None:
                obj = names.get(group["font"])
                current = cmaps.get(obj) if obj else None
                two_byte = bool(current) and max(current, default=0) > 0xFF
                continue
            if group["star"] is not None:
                pieces.append("\n")
                continue
            moved = group["y"] or group["my"]
            if moved is not None:
                try:
                    y = float(moved)
                except ValueError:
                    continue
                # A vertical move means a new line; a horizontal-only move is
                # kerning inside the same one.
                if last_y is not None and abs(y - last_y) > 1.5:
                    pieces.append("\n")
                last_y = y
                continue
            chunk = group["array"] or group["single"]
            for token in _STRING.findall(chunk):
                if token.startswith(b"<"):
                    digits = re.sub(rb"\s", b"", token[1:-1])
                    if len(digits) % 2:
                        digits += b"0"
                    data = bytes.fromhex(digits.decode("ascii", "ignore"))
                else:
                    data = _unescape(token[1:-1])
                pieces.append(_decode(data, current, two_byte))
            pieces.append(" ")

    text = "".join(pieces)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def legibility(text: str) -> float:
    """How much this looks like prose rather than glyph codes. Below ~0.85 is garbage.

    Counting "plausible characters" alone is not enough: text decoded with the
    wrong font map comes out as accented Latin letters, which look plausible one
    by one. What it never has is spaces — words only appear when the decoding is
    right — so the share of spaces is the signal that separates the two.
    """
    if not text:
        return 0.0
    plausible = sum(c.isalnum() or c.isspace() or c in ".,;:!?'\"·—–-|@()/&+%€$#" for c in text)
    spaces = text.count(" ") / len(text)
    return (plausible / len(text)) * min(1.0, spaces / 0.08)

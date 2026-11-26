"""Text extraction for uploaded evidence documents (PDF, Word, plain text, scanned pages and photos).

Everything runs in this process: pdfium for PDF text and page rendering, python-docx for Word, and Tesseract OCR for
scans when the `tesseract` binary is installed (it is in the Docker image). Nothing is sent to an outside service.

The file type is decided from the file's bytes, never from its name. The original file is not stored: the extracted
text becomes the immutable source body, and its provenance (name, type, size, SHA-256, method, pages) is kept on the
source so anyone can check which file the text came from."""
import hashlib
import io
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass, field

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30
MAX_CHARS = 20000  # same limit as pasted evidence; the extraction model reads one source per call
MAX_UNZIPPED = 60 * 1024 * 1024  # Word files are zip archives: refuse decompression bombs
MAX_PIXELS = 40_000_000
OCR_DPI = 300
MIN_TEXT_PER_PAGE = 25  # fewer extractable characters than this on average means a scanned PDF
OCR_LANGUAGES = "eng"

ACCEPT = ".pdf,.docx,.txt,.md,.eml,.png,.jpg,.jpeg,.tif,.tiff"


class DocumentError(Exception):
    """A file that cannot become evidence. `status` is the HTTP status the route should answer with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass
class ExtractedDocument:
    text: str
    method: str  # text | pdf_text | docx | ocr_pdf | ocr_image
    content_type: str
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def capabilities() -> dict:
    return {"accept": ACCEPT, "max_bytes": MAX_BYTES, "max_pages": MAX_PAGES, "max_chars": MAX_CHARS,
            "ocr": ocr_available()}


def sniff(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" in z.namelist():
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            pass
        return "application/zip"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/msword"  # legacy binary .doc
    return "text/plain"


def normalize(text: str) -> str:
    """Stable, readable text: NFC, Unix newlines, no control characters, trimmed lines, at most one blank line."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("­", "").replace("﻿", "")
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _plain(data: bytes) -> str:
    try:
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return data.decode("utf-16")
        if b"\x00" not in data:
            return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    raise DocumentError("Unsupported file. Upload a PDF, a Word (.docx) file, a UTF-8 text file or an image.", 415)


def _ocr_images(images) -> str:
    if not ocr_available():
        raise DocumentError("This file is a scan or a photo, so its text has to be recognised (OCR). OCR is not "
                            "installed on this server: use the Docker image, or install Tesseract.", 422)
    import pytesseract
    parts = []
    for img in images:
        parts.append(pytesseract.image_to_string(img.convert("L"), lang=OCR_LANGUAGES, timeout=60))
    return "\n\n".join(parts)


def _pdf(data: bytes) -> ExtractedDocument:
    import pypdfium2 as pdfium
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        raise DocumentError("The PDF could not be opened (damaged or password-protected).") from e
    try:
        n = len(pdf)
        if n == 0:
            raise DocumentError("The PDF has no pages.")
        if n > MAX_PAGES:
            raise DocumentError(f"The PDF has {n} pages; the limit is {MAX_PAGES}. Upload the relevant pages only.")
        texts = []
        for i in range(n):
            page = pdf[i]
            textpage = page.get_textpage()
            texts.append(textpage.get_text_range())
            textpage.close()
            page.close()
        text = "\n\n".join(texts)
        if len(normalize(text)) >= MIN_TEXT_PER_PAGE * n:
            return ExtractedDocument(text, "pdf_text", "application/pdf", n)
        # No usable text layer: a scanned document. Render each page and recognise it.
        images = []
        for i in range(n):
            page = pdf[i]
            images.append(page.render(scale=OCR_DPI / 72).to_pil())
            page.close()
        return ExtractedDocument(_ocr_images(images), "ocr_pdf", "application/pdf", n,
                                 ["Text recognised from scanned pages (OCR). Check it against the paper original."])
    finally:
        pdf.close()


def _docx(data: bytes) -> ExtractedDocument:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
            raise DocumentError("The Word file expands to more than 60 MB; refusing to open it.")
    import docx
    document = docx.Document(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:  # tables keep their row order; cells are joined with " | "
        for row in table.rows:
            cells = []
            for cell in row.cells:
                if not cells or cell.text != cells[-1]:  # merged cells repeat their text
                    cells.append(cell.text)
            lines.append(" | ".join(cells))
    warnings = []
    if any(rel.reltype.endswith("/image") for rel in document.part.rels.values()):
        warnings.append("Images inside the Word file were not read; only its text was extracted.")
    return ExtractedDocument("\n".join(lines), "docx", sniff(data), None, warnings)


def _image(data: bytes, content_type: str) -> ExtractedDocument:
    from PIL import Image, ImageSequence
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        frames = [f.copy() for _, f in zip(range(MAX_PAGES), ImageSequence.Iterator(img))]
    except (Image.DecompressionBombError, OSError) as e:
        raise DocumentError("The image could not be read or is too large.") from e
    return ExtractedDocument(_ocr_images(frames), "ocr_image", content_type, len(frames),
                             ["Text recognised from an image (OCR). Check it against the original."])


def extract(data: bytes) -> ExtractedDocument:
    if not data:
        raise DocumentError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise DocumentError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.", 413)
    kind = sniff(data)
    if kind == "application/pdf":
        doc = _pdf(data)
    elif kind.endswith("wordprocessingml.document"):
        doc = _docx(data)
    elif kind.startswith("image/"):
        doc = _image(data, kind)
    elif kind == "text/plain":
        doc = ExtractedDocument(_plain(data), "text", "text/plain")
    elif kind == "application/msword":
        raise DocumentError("Legacy .doc files are not supported. Save it as .docx or PDF and upload again.", 415)
    else:
        raise DocumentError("Unsupported file. Upload a PDF, a Word (.docx) file, a UTF-8 text file or an image.", 415)
    doc.text = normalize(doc.text)
    if len(doc.text) < 3:
        raise DocumentError("No readable text was found in this file.")
    if len(doc.text) > MAX_CHARS:
        raise DocumentError(f"The extracted text has {len(doc.text):,} characters; the limit for one source is "
                            f"{MAX_CHARS:,}. Split the document and upload the parts separately.")
    return doc


def provenance(filename: str | None, data: bytes, doc: ExtractedDocument) -> dict:
    name = (filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][:200]
    return {"filename": name, "content_type": doc.content_type, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "method": doc.method, "pages": doc.pages,
            "warnings": doc.warnings}


def default_title(filename: str | None) -> str:
    name = (filename or "Uploaded document").replace("\\", "/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    title = re.sub(r"[_\s]+", " ", stem).strip()
    return (title if len(title) >= 3 else "Uploaded document")[:300]

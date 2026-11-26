"""Uploaded documents become immutable, versioned evidence: text extracted locally, type sniffed from bytes,
provenance kept, the file itself discarded, and the same case visibility rules for who may upload."""
import io

import pytest

from app.services import documents as docs

EVA = "/api/cases/ONB-005"
REPORT = ("HR check-in, Eva Stone, 12 October 2026.\n"
          "Eva completed the mandatory compliance training.\n"
          "Two complex scenarios still need to be covered.")


def _pdf(lines: list[str]) -> bytes:
    """A minimal, valid one-page PDF. With no lines it has no text layer, like a scan."""
    text = "".join(f"BT /F1 12 Tf 72 {720 - 20 * i} Td ({line}) Tj ET\n" for i, line in enumerate(lines))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(text) + text.encode("latin-1") + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def _docx() -> bytes:
    import docx
    d = docx.Document()
    for line in REPORT.split("\n"):
        d.add_paragraph(line)
    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Ticket Portal", "requested"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _upload(client, data: bytes, name: str, url=f"{EVA}/documents", **form):
    return client.post(url, files={"file": (name, data, "application/octet-stream")}, data=form)


# ---------- extraction ----------

def test_plain_text_word_and_pdf_are_read_locally():
    assert docs.extract(REPORT.encode()).method == "text"
    word = docs.extract(_docx())
    assert word.method == "docx" and "compliance training" in word.text and "Ticket Portal | requested" in word.text
    pdf = docs.extract(_pdf(REPORT.split("\n")))
    assert pdf.method == "pdf_text" and pdf.pages == 1
    assert "Two complex scenarios still need to be covered." in pdf.text


def test_type_comes_from_the_bytes_not_the_name():
    assert docs.sniff(_pdf(["x"])) == "application/pdf"
    assert docs.sniff(_docx()).endswith("wordprocessingml.document")
    assert docs.sniff(b"\xd0\xcf\x11\xe0legacy") == "application/msword"
    with pytest.raises(docs.DocumentError, match="Legacy .doc"):
        docs.extract(b"\xd0\xcf\x11\xe0" + b"\x00" * 64)
    with pytest.raises(docs.DocumentError, match="Unsupported"):
        docs.extract(b"PK\x03\x04not a word file")
    with pytest.raises(docs.DocumentError, match="empty"):
        docs.extract(b"")


def test_scanned_pdf_needs_ocr_and_says_so(monkeypatch):
    monkeypatch.setattr(docs, "ocr_available", lambda: False)
    with pytest.raises(docs.DocumentError, match="OCR is not installed"):
        docs.extract(_pdf([]))


def test_scanned_pdf_is_recognised_when_ocr_is_installed(monkeypatch):
    import pytesseract
    seen = []
    monkeypatch.setattr(docs, "ocr_available", lambda: True)
    monkeypatch.setattr(pytesseract, "image_to_string",
                        lambda img, lang, timeout: seen.append(img.size) or "Eva completed the training.")
    doc = docs.extract(_pdf([]))
    assert doc.method == "ocr_pdf" and doc.text == "Eva completed the training." and doc.warnings
    assert seen and seen[0][0] > 2000  # rendered at OCR resolution (300 dpi)


def test_text_is_normalised_and_limits_hold(monkeypatch):
    assert docs.normalize("a\r\n\r\n\r\n\r\nb \x07\n") == "a\n\nb"
    with pytest.raises(docs.DocumentError, match="limit for one source"):
        docs.extract((("x" * 100 + "\n") * 300).encode())
    monkeypatch.setattr(docs, "MAX_BYTES", 10)
    with pytest.raises(docs.DocumentError) as e:
        docs.extract(b"x" * 11)
    assert e.value.status == 413


# ---------- upload routes ----------

def test_coordinator_uploads_a_report_to_a_case(login):
    coord = login("Elira Dervishi")
    r = _upload(coord, _pdf(REPORT.split("\n")), "Eva_HR_checkin.pdf", date="2026-10-12")
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["document"]["method"] == "pdf_text" and out["document"]["filename"] == "Eva_HR_checkin.pdf"
    assert len(out["document"]["sha256"]) == 64 and "Two complex scenarios" in out["text"]
    detail = coord.get(EVA).json()
    src = next(s for s in detail["sources"] if s["id"] == out["source"]["id"])
    assert src["kind"] == "document" and src["ingested_via"] == "upload" and src["title"] == "Eva HR checkin"
    assert src["date"] == "2026-10-12" and src["body"] == out["text"]  # the stored body is exactly the extraction
    assert src["document"]["sha256"] == out["document"]["sha256"]
    events = coord.get("/api/audit?entity=source").json()
    events = events["events"] if isinstance(events, dict) else events
    assert any(e["action"] == "uploaded" for e in events)


def test_uploaded_text_feeds_the_verifier_like_any_source(login, monkeypatch):
    from app.ai import client
    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client, "model_digest", lambda: "sha256:test")
    monkeypatch.setattr(client, "extract", lambda payload: {"claims": [
        {"scope": "complex_scenarios", "value": "coverage_pending",
         "quote": "Two complex scenarios still need to be covered.", "reference": None},
        {"scope": "initial_training", "value": "completed", "quote": "Eva finished everything.", "reference": None}]})
    coord = login("Elira Dervishi")
    sid = _upload(coord, _docx(), "checkin.docx").json()["source"]["id"]
    detail = coord.get(EVA).json()
    mine = [c for c in detail["claims"] if c["source_id"] == sid]
    assert [(c["scope"], c["value"]) for c in mine] == [("complex_scenarios", "coverage_pending")]
    body = next(s["body"] for s in detail["sources"] if s["id"] == sid)
    assert body[mine[0]["start"]:mine[0]["end"]] == mine[0]["quote"]
    assert any(x["reason"].startswith("no exact match") for x in detail["rejected"] if x["source_id"] == sid)


def test_who_may_upload_to_a_case(login):
    # The employee on their own case, and HR (summary view) may contribute; HR still cannot read bodies afterwards.
    assert _upload(login("Eva Stone"), REPORT.encode(), "note.txt").status_code == 201
    hr = login("Teuta Gjoni")
    r = _upload(hr, REPORT.encode(), "hr-report.txt")
    assert r.status_code == 201, r.text
    assert r.json()["text"] == REPORT  # the uploader sees what was extracted from their own file
    assert all("body" not in s or s["body"] is None for s in hr.get(EVA).json().get("sources", []))
    # Another employee: the case is hidden (404). Management reads summaries and cannot add evidence (403).
    assert _upload(login("Leo Marin"), REPORT.encode(), "x.txt").status_code == 404
    assert _upload(login("Mira Shehu"), REPORT.encode(), "x.txt").status_code == 403


def test_unreadable_files_are_refused_and_nothing_is_stored(login):
    coord = login("Elira Dervishi")
    before = len(coord.get(EVA).json()["sources"])
    r = _upload(coord, b"\xd0\xcf\x11\xe0" + b"\x00" * 64, "old.doc")
    assert r.status_code == 415 and "docx" in r.json()["detail"]
    assert len(coord.get(EVA).json()["sources"]) == before


def test_inbox_upload_is_matched_to_a_case(login):
    coord = login("Elira Dervishi")
    r = _upload(coord, REPORT.encode(), "Eva Stone check-in.txt", url="/api/inbox/documents",
                author_role="HR Business Partner", date="2026-10-12")
    assert r.status_code == 201, r.text
    assert r.json()["matched_case"]["ref"] == "ONB-005" and r.json()["source"]["ingested_via"] == "upload"
    assert _upload(login("Ardit Kola"), REPORT.encode(), "x.txt", url="/api/inbox/documents",
                   author_role="Technical Lead", date="2026-10-12").status_code == 403


def test_capabilities_report_ocr(login, monkeypatch):
    monkeypatch.setattr(docs, "ocr_available", lambda: False)
    caps = login("Eva Stone").get("/api/documents/capabilities").json()
    assert caps["ocr"] is False and ".pdf" in caps["accept"] and caps["max_chars"] == 20000

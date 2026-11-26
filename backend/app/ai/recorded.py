"""Recorded extractions for the showcase data (data/showcase.json), keyed by the SHA-256 of the exact body.

Like the starter-pack examples in cache/replay/, they are replayed through the same verifier and labelled
"Recorded example", never presented as a live model response, and only for a body whose hash matches exactly.
This module reads JSON only: it has no import path to any writer."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

SHOWCASE = Path(__file__).resolve().parents[3] / "data" / "showcase.json"


def _response(rows) -> dict:
    return {"claims": [{"scope": s, "value": v, "quote": q, "reference": r} for s, v, q, r in rows]}


@lru_cache
def _by_sha() -> dict[str, dict]:
    if not SHOWCASE.is_file():
        return {}
    data = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    out = {}
    for item in data.get("sources", []) + data.get("inbox", []):
        out[hashlib.sha256(item["body"].encode("utf-8")).hexdigest()] = _response(item.get("claims", []))
    for doc in data.get("documents", []):
        out[hashlib.sha256(doc["text"].encode("utf-8")).hexdigest()] = _response(doc.get("claims", []))
    return out


def lookup(body_sha256: str) -> dict | None:
    return _by_sha().get(body_sha256)

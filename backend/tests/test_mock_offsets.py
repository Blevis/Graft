"""Guards the frontend mock: every claim offset must slice its quote out of the immutable body exactly once."""
import json
from pathlib import Path

MOCK = Path(__file__).resolve().parents[2] / "frontend" / "src" / "mocks" / "case-ONB-005.json"


def test_onb005_mock_claim_offsets():
    detail = json.loads(MOCK.read_text(encoding="utf-8"))
    bodies = {s["id"]: s["body"] for s in detail["sources"]}
    assert len(detail["claims"]) == 6
    for c in detail["claims"]:
        body = bodies[c["source_id"]]
        assert body[c["start"]:c["end"]] == c["quote"], c["id"]
        assert body.count(c["quote"]) == 1, c["id"]
    for r in detail["rejected"]:
        assert r["raw"]["quote"] not in bodies[r["source_id"]]

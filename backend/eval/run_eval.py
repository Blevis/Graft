"""Evaluate the production pipeline and HTTP routes on a fresh, fictional SQLite dataset.

From backend: python -m eval.run_eval --mode replay   (or --mode live).
See docs/eval.md for the optional fixture format, output paths and exit codes.
"""
import argparse
import json
import hashlib
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
RESULTS = BACKEND / "eval/results"
RUNS = BACKEND / "eval/runs"
COORD = "Elira Dervishi"
DEFAULT_PROBES = (
    ("eva-action", "agent", "ONB-005", None),
    ("leo-action", "agent", "ONB-002", None),
    ("lina-action", "agent", "ONB-009", None),
    ("eva-evidence", "ask", "ONB-005", "What does the technical lead say about Eva's complex scenarios?"),
    ("eva-readiness", "ask", "ONB-005", "Decide whether Eva is ready for onboarding closure."),
    ("unsupported", "ask", "ONB-005", "What is Eva's favourite film?"),
)


class Fixture(BaseModel):
    """One optional business-owner-authored expectation; all strings use source/case refs."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    kind: Literal["extract", "agent", "ask"]
    source: str | None = None
    case: str | None = None
    question: str | None = None
    actor: str = COORD
    # Each claim pattern is a subset of scope/value/reference/quote to match exactly.
    contains_claims: list[dict] = []
    excludes_claims: list[dict] = []
    cited_refs: list[str] = []
    text_contains: list[str] = []
    refused: bool | None = None

    @model_validator(mode="after")
    def check_target(self):
        patterns = self.contains_claims + self.excludes_claims
        if self.kind == "extract":
            if not self.source or not patterns or any((self.case, self.question, self.cited_refs,
                                                       self.text_contains, self.refused is not None)):
                raise ValueError("extract requires source and a claim expectation")
            for pattern in patterns:
                if not pattern or not set(pattern) <= {"scope", "value", "quote", "reference"}:
                    raise ValueError("invalid claim pattern")
        else:
            if self.source or patterns or not any((self.cited_refs, self.text_contains, self.refused is not None)):
                raise ValueError("agent/ask needs cited_refs, text_contains or refused")
            if self.kind == "agent" and (not self.case or self.question or self.refused is not None):
                raise ValueError("agent requires case, without question/refused")
            if self.kind == "ask" and not self.question:
                raise ValueError("ask requires a question")
        return self


def expectations(folder):
    entries = []
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data if isinstance(data, list) else [data]:
            entries.append(Fixture.model_validate(row))
    if len(entries) != len({f.id for f in entries}):
        raise ValueError("Duplicate fixture IDs")
    return entries


def run_extractions(org_id, mode):
    from sqlalchemy import select
    from app.ai.pipeline import analyze_source
    from app.ai.verifier import verify
    from app.db import SessionLocal
    from app.models import AnalysisRun, EmployeeCase, Source
    from app.services.rules import recompute_case

    rows = {}
    with SessionLocal() as db:
        sources = db.scalars(select(Source).where(Source.org_id == org_id).order_by(Source.ref)).all()
        if {s.ref for s in sources} != {f"E{i}" for i in range(1, 9)}:
            raise ValueError("The demo evidence set must contain E1 through E8")
        for source in sources:
            outcome = analyze_source(db, source, ai_enabled=True, allow_live=mode == "live")
            attempts = db.scalars(select(AnalysisRun).where(
                AnalysisRun.source_id == source.id, AnalysisRun.mode == "live"
            ).order_by(AnalysisRun.created_at)).all()
            raw = outcome.run.raw_response if outcome.run else None
            verified = verify(source.body, raw, source.ref) if raw is not None else None
            rows[source.ref] = {
                "source_id": source.id, "body_sha256": source.body_sha256,
                "served_mode": outcome.served_mode, "note": outcome.note,
                "model": outcome.run.model if outcome.run else None,
                "prompt_version": outcome.run.prompt_version if outcome.run else None,
                "raw_served": raw, "accepted": verified.accepted if verified else [],
                "rejected": verified.rejected if verified else [],
                "live_attempts": [{"model": r.model, "prompt_version": r.prompt_version, "status": r.status,
                                   "error": r.error, "raw_response": r.raw_response} for r in attempts],
            }
        for case in db.scalars(select(EmployeeCase).where(EmployeeCase.org_id == org_id)):
            recompute_case(db, case)
        db.commit()
    return rows


def login(client, accounts, name):
    matches = [r for r in accounts if r["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Unknown or ambiguous fixture actor: {name}")
    client.post("/api/auth/demo-login", json={"user_id": matches[0]["user_id"]}).raise_for_status()


def run_probe(client, fixture):
    if fixture.kind == "agent":
        case_url = f"/api/cases/{fixture.case}"
        before = client.get(case_url)
        response = client.post(f"{case_url}/agent-runs")
    else:
        payload = {"question": fixture.question}
        if fixture.case:
            payload["case_id"] = fixture.case
        response = client.post("/api/ask", json=payload)
    data = response.json()
    output = {"http": response.status_code, "response": data, "cited_refs": [], "checks": {}}
    if response.status_code != 200 and response.status_code != 201:
        output["mode"] = "error"
        return output
    if fixture.kind == "agent":
        output["mode"] = {"completed": "live", "failed": "failed", "unavailable": "unavailable"}.get(
            data.get("status"), "error")
    else:
        output["mode"] = data.get("mode", "error")
    if fixture.kind == "agent":
        # Verify persistence and human-owned records through ordinary subsequent requests.
        after = client.get(case_url)
        history = client.get(f"{case_url}/agent-runs")
        output["checks"]["persisted_in_history"] = history.is_success and any(
            r == data for r in history.json())
        output["checks"]["human_records_preserved"] = before.is_success and after.is_success and all(
            before.json()[field] == after.json()[field] for field in ("tasks", "reviews"))
    if output["mode"] == "unavailable":
        if fixture.kind == "agent":
            output["checks"]["no_proposals"] = data.get("proposals") == []
        else:
            output["checks"]["unavailable_refusal"] = data.get("refused") is True and data.get("citations") == []
        return output
    # Validate citations independently using GETs as the same actor.
    if fixture.case:
        case_refs = [fixture.case]
    else:
        cases = client.get("/api/cases?view=all")
        cases.raise_for_status()
        case_refs = [case["ref"] for case in cases.json()]
    sources, claims = {}, {}
    if not fixture.case:
        # The org-wide inbox may include project-only E8. Visibility is enforced by the API.
        inbox = client.get("/api/inbox")
        inbox.raise_for_status()
        sources = {item["source"]["id"]: item["source"] for item in inbox.json()}
    for ref in case_refs:
        detail = client.get(f"/api/cases/{ref}")
        detail.raise_for_status()
        obj = detail.json()
        sources.update((s["id"], s) for s in obj["sources"])
        claims.update((c["id"], c) for c in obj["claims"])
    cited = set()
    if fixture.kind == "agent":
        proposals = data.get("proposals", [])
        valid = bool(proposals)
        for p in proposals:
            src, cl = p.get("cited_source_ids", []), p.get("cited_claim_ids", [])
            valid &= bool(src or cl) and set(src) <= sources.keys() and set(cl) <= claims.keys()
            cited.update(src)
            cited.update(claims[id_]["source_id"] for id_ in cl if id_ in claims)
        output["checks"].update(completed=data.get("status") == "completed",
                                one_to_three=1 <= len(proposals) <= 3, case_citations=valid)
    else:
        citations = data.get("citations", [])
        valid = bool(citations) or data.get("refused") is True
        for citation in citations:
            id_, quote, claim = citation.get("source_id"), citation.get("quote"), citation.get("claim_id")
            valid &= id_ in sources and isinstance(quote, str) and bool(quote) and sources[id_]["body"].count(quote) == 1
            valid &= claim is None or (claim in claims and claims[claim]["source_id"] == id_)
            cited.add(id_)
        output["checks"] = {"grounded_citations_or_refusal": valid}
    output["cited_refs"] = sorted(sources[id_]["ref"] for id_ in cited if id_ in sources and sources[id_]["ref"])
    return output


def assess(fixture, result, eligible):
    if not eligible:
        return "blocked"
    if fixture.kind == "extract":
        def matches(pattern):
            return any(all(claim[k] == v for k, v in pattern.items()) for claim in result["accepted"])
        ok = all(matches(p) for p in fixture.contains_claims) and not any(matches(p) for p in fixture.excludes_claims)
    else:
        obj = result["response"]
        if fixture.kind == "agent":
            words = " ".join(p["title"] + " " + p["body"] for p in obj.get("proposals", []))
        else:
            words = obj.get("answer", "")
        ok = all(result["checks"].values()) and bool(result["checks"])
        ok &= set(fixture.cited_refs) <= set(result["cited_refs"])
        ok &= all(term.casefold() in words.casefold() for term in fixture.text_contains)
        ok &= fixture.refused is None or obj.get("refused") is fixture.refused
    return "pass" if ok else "fail"


def evaluate(mode, fixtures):
    from fastapi.testclient import TestClient
    from app.ai import client as provider
    from app.db import Base, SessionLocal, engine
    from app.main import create_app
    from app.seed.seed import seed_demo

    app = create_app()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        org = seed_demo(db)
        db.commit()
        org_id = org.id
    extracted = run_extractions(org_id, mode)
    results = {"requested_mode": mode, "configured": provider.is_configured(), "extraction": extracted,
               "probes": {}, "fixtures": {}, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with TestClient(app) as client:
        accounts = client.get("/api/auth/demo-accounts").json()
        login(client, accounts, COORD)
        eva = client.get("/api/cases/ONB-005")
        eva.raise_for_status()
        sources = {s["id"]: s["ref"] for s in eva.json()["sources"]}
        linked = any(f["rule_id"] == "CLOSURE_CONFLICT" and
                     {sources.get(c["source_id"]) for c in f["evidence"]} == {"E3", "E4"}
                     for f in eva.json()["findings"])
        results["eva_conflict"] = {"observed": linked, "evidence_modes":
                                   {s: extracted[s]["served_mode"] for s in ("E3", "E4")}}
        # These are smoke probes. Only supplied expectations receive business pass/fail scores.
        observed = {}
        for label, kind, case, question in DEFAULT_PROBES:
            probe = Fixture.model_construct(id=label, kind=kind, case=case, question=question)
            result = run_probe(client, probe)
            if kind == "ask" and result["mode"] == "live":
                answer = result["response"]
                if label == "eva-evidence":
                    result["checks"]["answers_with_e3"] = not answer.get("refused") and "E3" in result["cited_refs"]
                elif label == "eva-readiness":
                    result["checks"]["decision_deferred"] = (answer.get("refused") is True and
                                                             "technical owner" in answer.get("answer", "").casefold())
                elif label == "unsupported":
                    result["checks"]["unsupported_refused"] = answer.get("refused") is True
            observed[(COORD, kind, case, question)] = result
            results["probes"][label] = result
        for f in fixtures:
            if f.kind == "extract":
                result = extracted[f.source]
                eligible = result["served_mode"] == mode
                actual = result["served_mode"]
            else:
                login(client, accounts, f.actor)
                key = (f.actor, f.kind, f.case, f.question)
                if key not in observed:
                    observed[key] = run_probe(client, f)
                result = observed[key]
                actual = result["mode"]
                eligible = actual in {"live", "failed", "error"}
            results["fixtures"][f.id] = {"fixture": f.model_dump(exclude_defaults=True), "mode": actual,
                                         "evaluation_mode": actual if eligible and actual in {"live", "replay"} else None,
                                         "verdict": assess(f, result, eligible)}
            if f.kind != "extract":
                results["fixtures"][f.id]["output"] = result
    engine.dispose()
    return results


def archive_live(run):
    # This archive contains provider payloads only. Replays are available in the separate full run.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = RUNS / f"live_extraction_{stamp}.json"
    sources = []
    for ref, result in run["extraction"].items():
        attempts = result["live_attempts"]
        sources.append({
            "source": ref, "body_sha256": result["body_sha256"], "served_mode": result["served_mode"],
            "live_attempts": attempts, "raw_response": attempts[-1]["raw_response"] if attempts else None,
            "note": result["note"],
        })
    modes = run["eva_conflict"]["evidence_modes"]
    archive = {"created_utc": run["created_utc"], "provider_configured": run["configured"], "sources": sources,
               "eva_live_closure_conflict": run["eva_conflict"]["observed"] if set(modes.values()) == {"live"} else None,
               "eva_observed_closure_conflict": run["eva_conflict"]}
    RUNS.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(archive, handle, indent=2)
        handle.write("\n")
    run["live_archive"] = path.relative_to(BACKEND).as_posix()


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    fixture_id: str
    verdict: Literal["pass", "fail"]
    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def manual_review(snapshot, review_path):
    data = snapshot.read_bytes()
    run = json.loads(data)
    if run["requested_mode"] not in {"live", "replay"}:
        raise ValueError("--snapshot must be an original live or replay result")
    reviews = {}
    for item in json.loads(review_path.read_text(encoding="utf-8")):
        review = HumanReview.model_validate(item)
        if review.fixture_id in reviews or review.fixture_id not in run["fixtures"]:
            raise ValueError(f"Duplicate or unknown reviewed fixture {review.fixture_id}")
        reviews[review.fixture_id] = review
    output = {}
    for id_, fixture in run["fixtures"].items():
        review = reviews.get(id_)
        mode = fixture["mode"]
        if review and mode not in {"live", "replay"}:
            raise ValueError(f"Fixture {id_} has no model output to review (served: {mode})")
        output[id_] = {"fixture": fixture["fixture"], "mode": mode,
                       "evaluation_mode": "manual" if review else None,
                       "verdict": review.verdict if review else "blocked",
                       "reason": review.reason if review else "Human review pending",
                       "reviewer": review.reviewer if review else None}
    return {"requested_mode": "manual", "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_run": snapshot.name, "source_sha256": hashlib.sha256(data).hexdigest(), "fixtures": output}


def fixture_table(run):
    rows = run["fixtures"]
    counts = Counter(f["verdict"] for f in rows.values())
    out = ["", f"**Business-fixture totals:** {counts['pass']} passed, {counts['fail']} failed, "
               f"{counts['blocked']} blocked; {len(rows)} supplied."]
    if rows:
        out.extend(["", "| Fixture | Evaluation mode | Served mode | Verdict |", "| --- | --- | --- | --- |"])
        for key, f in rows.items():
            out.append(f"| {key} | {f.get('evaluation_mode') or 'unscored'} | {f['mode']} | {f['verdict']} |")
    else:
        out.extend(["", "No business-owner fixture files were supplied. Their accuracy remains unmeasured."])
    out.append("")
    return out


def markdown(runs):
    lines = ["# Evaluation of Graft's AI features", "",
             "Each run starts with a new, isolated SQLite database and the eight fictional starter-pack sources. "
             "The case agent and Ask Graft run through their HTTP routes as signed-in demo users. "
             "The live command requests Groq. The replay command disables provider access for the process.", ""]
    for run in runs:
        mode = run["requested_mode"]
        if mode == "manual":
            lines.extend(["## Human review", "",
                          f"Recorded {run['created_utc']}, reviewing `{run['source_run']}`, "
                          f"SHA-256 `{run['source_sha256']}`. "
                          "[Reviewers and rationales](../backend/eval/results/manual.json)."])
            lines.extend(fixture_table(run))
            continue
        rows = run["extraction"]
        counts = Counter(r["served_mode"] for r in rows.values())
        live_count = counts["live"]
        lines.extend([f"## {mode.capitalize()} run", "",
                      f"Recorded {run['created_utc']} · Groq key {'configured' if run['configured'] else 'absent'}. "
                      f"Fresh Groq extractions: **{live_count}/{len(rows)}**. "
                      f"[Raw outputs and traces](../backend/eval/results/{mode}.json).", ""])
        if "live_archive" in run:
            lines.extend([f"[Timestamped Groq extraction payloads](../backend/{run['live_archive']}).", ""])
        if mode == "live" and live_count < len(rows):
            lines.extend(["Live extraction coverage is incomplete. Fallback outputs are identified below. "
                          "Each source's `live_attempts` in the raw file lists model payloads actually received "
                          "and retained by the application.", ""])
        lines.extend(["| Source | Actual mode | Verified claims | Rejected candidates |",
                      "| --- | --- | ---: | ---: |"])
        for ref, r in rows.items():
            has_data = r["raw_served"] is not None
            lines.append(f"| {ref} | {r['served_mode']} | {len(r['accepted']) if has_data else '—'} "
                         f"| {len(r['rejected']) if has_data else '—'} |")
        conflict = run["eva_conflict"]
        paired = ", ".join(f"{ref}: {value}" for ref, value in conflict["evidence_modes"].items())
        lines.extend(["", f"Eva's same-day E3/E4 closure conflict: **{'detected' if conflict['observed'] else 'missing'}** "
                          f"({paired}).", ""])
        e3 = rows["E3"]
        for rejection in e3["rejected"]:
            lines.extend([f"E3 {e3['served_mode']} rejected {json.dumps(rejection['raw'].get('quote'), ensure_ascii=False)} "
                          f"with reason `{rejection['reason']}`. Only accepted claims feed the conflict rule. "
                          + ("The recorded E3 example deliberately includes this bad candidate."
                             if e3["served_mode"] == "replay" else ""), ""])
        lines.extend(["| API probe | HTTP | Actual mode | Mechanical checks |",
                      "| --- | ---: | --- | --- |"])
        for name, probe in run["probes"].items():
            checks = ", ".join(f"{label}={value}" for label, value in probe["checks"].items())
            lines.append(f"| {name} | {probe['http']} | {probe['mode']} | {checks or 'No answer or proposal scored'} |")
        lines.extend(fixture_table(run))
    lines.extend(["## Reproduce", "",
                  "From the repository root, activate the backend environment and run:", "",
                  "```bash", "cd backend", "python -m eval.run_eval --mode replay",
                  "python -m eval.run_eval --mode live", "```", "",
                  "Live mode reads `GROQ_API_KEY` from the environment or local .env. Existing development and "
                  "production databases are untouched. Live mode always archives provider payloads in "
                  "`backend/eval/runs/live_extraction_<UTC>.json`. A null payload means no live response was "
                  "recorded for that source. Results for each mode replace that mode's summary JSON file, "
                  "and the report shows the latest available run of each mode. Exit 1 signals a failed check. "
                  "Exit 2 signals incomplete live extraction, API or business-fixture coverage. A replay without business fixtures checks the "
                  "seeded evidence behavior only.", "",
                  "Human review of an existing scored run uses "
                  "`python -m eval.run_eval --mode manual --snapshot eval/results/live.json --reviews reviews.json`. "
                  "The review file is a JSON array with one object per assessed fixture "
                  "(`fixture_id`, `reviewer`, `verdict` equal to pass or fail, and `reason`). The report identifies "
                  "the originating run by SHA-256, records each review separately, and leaves missing verdicts "
                  "unscored. A human review requires an actual live or replay output for that fixture.", "",
                  "## Business-owner fixtures", "",
                  "The runner reads JSON objects or arrays of them from `backend/eval/fixtures/*.json`. "
                  "An alternative directory is accepted via `--fixtures`. Every object requires a unique `id` "
                  "and `kind`. Supported fields:", "",
                  "| Kind | Target | Expectations |", "| --- | --- | --- |",
                  "| extract | `source` (E1–E8) | `contains_claims` and/or `excludes_claims`, arrays of partial "
                  "exact claim objects with scope, value, reference or quote. |",
                  "| agent | `case` (e.g. ONB-005) | `cited_refs` and/or `text_contains`, arrays of strings. |",
                  "| ask | `question`, optionally `case` | `refused` (boolean), `cited_refs`, and/or `text_contains`. |", "",
                  "Example input: `{\"id\":\"eva-gap\",\"kind\":\"extract\",\"source\":\"E3\",\"contains_claims\":"
                  "[{\"scope\":\"complex_scenarios\",\"value\":\"coverage_pending\"}]}`. "
                  "For agent and Ask fixtures, `actor` can name a seeded demo account; the default is Elira Dervishi. "
                  "The runner independently checks returned source IDs, claim IDs and exact Ask quote text through that "
                  "actor's visible cases. Text checks use case-insensitive substring matching; reviewers should read "
                  "the raw traces before treating a matching phrase as evidence of a useful recommendation.", ""])
    return "\n".join(lines)


def verdict(run):
    failed = any(row["verdict"] == "fail" for row in run["fixtures"].values())
    if run["requested_mode"] == "manual":
        if failed:
            return 1
        return 2 if not run["fixtures"] or any(f["verdict"] == "blocked" for f in run["fixtures"].values()) else 0
    failed |= not run["eva_conflict"]["observed"]
    for probe in run["probes"].values():
        failed |= probe["mode"] in ("error", "failed") or not all(probe["checks"].values())
    if failed:
        return 1
    if run["requested_mode"] == "live":
        incomplete = not run["fixtures"] or any(row["served_mode"] != "live" for row in run["extraction"].values())
        incomplete |= any(p["mode"] == "unavailable" for p in run["probes"].values())
        incomplete |= any(f["verdict"] == "blocked" for f in run["fixtures"].values())
        if incomplete:
            return 2
    return 0


def main():
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["live", "replay", "manual"])
    parser.add_argument("--fixtures", type=Path, default=BACKEND / "eval/fixtures")
    parser.add_argument("--snapshot", type=Path, help="Prior evaluator JSON to be human-reviewed")
    parser.add_argument("--reviews", type=Path, help="Human verdicts for fixtures in that snapshot")
    args = parser.parse_args()
    if args.mode == "manual":
        if not args.snapshot or not args.reviews:
            parser.error("manual mode requires --snapshot and --reviews")
        run = manual_review(args.snapshot, args.reviews)
    else:
        if args.snapshot or args.reviews:
            parser.error("--snapshot and --reviews belong to manual mode")
        fixtures = expectations(args.fixtures)
        # Match backend development settings even if the Compose file has an empty key.
        load_dotenv(BACKEND / ".env", override=False)
        load_dotenv(ROOT / ".env", override=False)
        with TemporaryDirectory(prefix="graft-eval-") as folder:
            # Set before importing app.db, which constructs its engine at import time.
            os.environ.update(DATABASE_URL=f"sqlite:///{folder}/eval.sqlite", DEMO_MODE="true", AUTH_MODE="demo")
            if args.mode == "replay":
                os.environ["GROQ_API_KEY"] = ""
            run = evaluate(args.mode, fixtures)
        if args.mode == "live":
            archive_live(run)
    RESULTS.mkdir(parents=True, exist_ok=True)
    # Always UTF-8: the platform default on Windows (cp1252) corrupts quotes copied from the sources.
    (RESULTS / f"{args.mode}.json").write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    runs = [json.loads(p.read_text(encoding="utf-8"))
            for p in (RESULTS / f"{m}.json" for m in ("live", "replay", "manual")) if p.exists()]
    report = ROOT / "docs/eval.md"
    report.parent.mkdir(exist_ok=True)
    report.write_text(markdown(runs), encoding="utf-8")
    count = Counter(r["served_mode"] for r in run.get("extraction", {}).values())
    print(f"{args.mode}: {dict(count)}; fixtures supplied: {len(run['fixtures'])}; report: {report}")
    return verdict(run)


if __name__ == "__main__":
    raise SystemExit(main())

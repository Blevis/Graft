"""The figures behind the Insights charts are counts over the caller's visible cases, never more."""


def test_chart_figures_for_the_coordinator(login):
    d = login("Elira Dervishi").get("/api/insights").json()
    assert sum(t["count"] for t in d["tracker"]["by_status"]) == d["totals"]["cases"] == 10
    assert sum(d["tracker"]["age"].values()) == 10
    assert len(d["progress"]) == 10 and all(0 <= p["met"] <= p["required"] for p in d["progress"])
    assert d["checks"] == {"met": sum(p["met"] for p in d["progress"]), "required": sum(p["required"] for p in d["progress"])}
    # Access: the three systems on Leo Marin's case, none of them confirmed usable yet.
    states = {a["state"]: a["count"] for a in d["access"]["by_state"]}
    assert d["access"]["systems"] == 3 and states["confirmed_usable"] == 0 and d["access"]["cases_blocked"] == 1
    # Evidence: one bucket per day, ending on the as-of date; totals agree with the per-kind split.
    assert len(d["evidence"]["by_day"]) == 28 and d["evidence"]["by_day"][-1]["date"] == d["as_of_date"]
    assert sum(k["count"] for k in d["evidence"]["by_kind"]) == d["evidence"]["sources"]
    assert d["evidence"]["claims"] > 0 and d["evidence"]["rejected"] >= 1


def test_summary_viewer_gets_counts_but_no_claim_figures(login):
    d = login("Mira Shehu").get("/api/insights").json()  # management viewer: summaries only
    assert d["totals"]["cases"] == 10 and d["evidence"]["sources"] > 0
    assert d["evidence"]["claims"] == 0 and d["evidence"]["rejected"] == 0 and d["evidence"]["claim_sources"] == 0


def test_employee_figures_cover_only_their_case(login):
    d = login("Eva Stone").get("/api/insights").json()
    assert [p["ref"] for p in d["progress"]] == ["ONB-005"]
    assert d["access"]["systems"] == 0 and d["evidence"]["sources"] == 2
    assert d["evidence"]["rejected"] == 0  # rejected candidates are for the full case team only


def test_workload_and_due_buckets_follow_open_tasks(login):
    coordinator = login("Elira Dervishi")
    case = coordinator.get("/api/cases/ONB-005").json()
    owner = case["case"]["tech_owner"]["id"]
    r = coordinator.post("/api/cases/ONB-005/tasks", json={
        "title": "Plan coverage of the complex scenarios", "owner_user_id": owner, "due_date": "2026-10-01",
        "cited_source_ids": [case["sources"][0]["id"]]})
    assert r.status_code in (200, 201), r.text
    d = coordinator.get("/api/insights").json()
    assert d["due"]["overdue"] == 1 and sum(d["due"].values()) == d["totals"]["open_tasks"] == 1
    assert d["workload"] == [{"owner": "Ardit Kola", "open": 1, "overdue": 1}]

"""Frontend ↔ backend contract tests.

These assert that each endpoint the React frontend consumes returns the exact
top-level keys the TypeScript types depend on (frontend/src/types/*). If the
backend schema drifts, these fail loudly before the frontend breaks at runtime.
"""

from datetime import datetime, timedelta, timezone

RECENT_ISO = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

# Mirrors frontend/src/types/lead.ts `Lead` / LeadResponse.
LEAD_RESPONSE_KEYS = {
    "id",
    "company_name",
    "industry",
    "location",
    "company_size",
    "company_website",
    "signal_type",
    "signal_title",
    "signal_description",
    "signal_date",
    "source_name",
    "source_url",
    "technologies",
    "project_name",
    "project_value",
    "estimated_hiring",
    "hiring_roles",
    "poc_name",
    "poc_title",
    "poc_linkedin_url",
    "public_contact",
    "signal_confidence",
    "lead_score",
    "lead_priority",
    "opportunity_summary",
    "recommended_action",
    "recommended_pitch",
    "status",
    "created_at",
    "updated_at",
    "last_verified_at",
}

ANALYZE_PAYLOAD = {
    "company_name": "Contract Test Co",
    "industry": "IT",
    "signal_title": "Hiring ramp",
    "signal_description": "Hiring 30 Java and AWS engineers for a new project.",
    "technologies": ["Java", "AWS"],
    "estimated_hiring": 30,
    "signal_date": RECENT_ISO,
}


def _assert_superset(actual: dict, required: set, label: str):
    missing = required - set(actual.keys())
    assert not missing, f"{label} is missing keys required by the frontend: {sorted(missing)}"


def test_health_contract(client):
    body = client.get("/health").json()
    _assert_superset(body, {"status", "app", "environment", "version"}, "GET /health")


def test_create_lead_contract(client):
    resp = client.post("/leads", json={"company_name": "Acme", "industry": "IT"})
    assert resp.status_code == 201
    _assert_superset(resp.json(), LEAD_RESPONSE_KEYS, "POST /leads")


def test_list_leads_contract(client):
    client.post("/leads", json={"company_name": "Acme", "industry": "IT"})
    body = client.get("/leads").json()
    _assert_superset(body, {"items", "total", "page", "page_size", "total_pages"}, "GET /leads")
    assert body["items"], "expected at least one lead"
    _assert_superset(body["items"][0], LEAD_RESPONSE_KEYS, "GET /leads items[]")


def test_get_lead_contract(client):
    lead_id = client.post("/leads", json={"company_name": "Acme"}).json()["id"]
    _assert_superset(client.get(f"/leads/{lead_id}").json(), LEAD_RESPONSE_KEYS, "GET /leads/{id}")


def test_update_lead_contract(client):
    lead_id = client.post("/leads", json={"company_name": "Acme"}).json()["id"]
    resp = client.put(f"/leads/{lead_id}", json={"status": "CONTACTED"})
    assert resp.status_code == 200
    _assert_superset(resp.json(), LEAD_RESPONSE_KEYS, "PUT /leads/{id}")
    assert resp.json()["status"] == "CONTACTED"


def test_delete_lead_contract(client):
    lead_id = client.post("/leads", json={"company_name": "Acme"}).json()["id"]
    assert client.delete(f"/leads/{lead_id}").status_code == 204
    assert client.get(f"/leads/{lead_id}").status_code == 404


def test_analyze_contract(client):
    resp = client.post("/leads/analyze", json=ANALYZE_PAYLOAD)
    assert resp.status_code in (200, 201)
    body = resp.json()
    # Mirrors frontend/src/types/lead.ts `LeadAnalysis`.
    _assert_superset(
        body,
        {
            "lead_id",
            "company_name",
            "signal_analysis",
            "opportunity_analysis",
            "scoring_result",
            "poc_recommendation",
            "pitch_result",
            "final_score",
            "priority",
            "recommended_action",
            "status",
            "already_existed",
        },
        "POST /leads/analyze",
    )
    _assert_superset(
        body["opportunity_analysis"],
        {"opportunity_type", "potential_staffing_need", "urgency", "opportunity_confidence"},
        "opportunity_analysis",
    )
    _assert_superset(body["scoring_result"], {"score", "priority", "score_breakdown"}, "scoring_result")
    _assert_superset(
        body["poc_recommendation"],
        {"primary_role", "secondary_roles", "recommendation_confidence"},
        "poc_recommendation",
    )
    _assert_superset(
        body["pitch_result"],
        {
            "email_subject",
            "opening_message",
            "value_proposition",
            "recommended_pitch",
            "call_to_action",
            "linkedin_message",
            "call_talking_points",
            "message_strategy",
            "confidence",
        },
        "pitch_result",
    )

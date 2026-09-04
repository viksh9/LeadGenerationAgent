from enrichment.poc_finder import find_points_of_contact
from intelligence.signal_detector import DetectedSignal


def test_known_vp_is_ranked_as_decision_maker():
    contacts = find_points_of_contact(
        company_name="Northwind Logistics",
        domain="northwindlogistics.example",
        signals=[],
        known_contacts=[
            {
                "full_name": "Priya Raman",
                "title": "VP of Operations",
                "email": "priya.raman@northwindlogistics.example",
            },
            {
                "full_name": "Sam Lee",
                "title": "Operations Manager",
            },
        ],
    )
    assert contacts[0].full_name == "Priya Raman"
    assert contacts[0].is_decision_maker is True
    assert contacts[0].seniority == "vp"


def test_synthetic_role_when_no_contacts():
    signal = DetectedSignal(
        signal_type="tech_stack",
        title="Legacy POS",
        description=None,
        source=None,
        source_url=None,
        strength=0.6,
        observed_at=None,
        intent_tags=["tech_stack", "stack_change"],
        buying_stage="consideration",
    )
    contacts = find_points_of_contact("Harbor Retail", "harborretail.example", [signal], [])
    assert len(contacts) == 1
    assert "Technology" in contacts[0].title or "CTO" in (contacts[0].title or "")
    assert contacts[0].is_decision_maker is True

"""Unit tests for the Phase 1 SignalDetector engine."""

import pytest

from database.models import SignalType
from intelligence.signal_detector import (
    STRONG,
    WEAK,
    SignalDetectionInput,
    SignalDetectionResult,
    SignalDetector,
    run_signal_detection,
)

detector = SignalDetector()


def analyze(**fields) -> SignalDetectionResult:
    return detector.detect(**fields)


# 1 -------------------------------------------------------------------------
def test_hiring_detection():
    result = analyze(signal_description="We are hiring backend engineers and developers.")
    assert SignalType.HIRING in result.signal_types


# 2 -------------------------------------------------------------------------
def test_project_award_detection():
    result = analyze(signal_title="Vendor selected", signal_description="We were awarded the contract.")
    assert SignalType.PROJECT_AWARD in result.signal_types


# 3 -------------------------------------------------------------------------
def test_project_execution_detection():
    result = analyze(signal_description="The implementation and rollout of the new system is underway.")
    assert SignalType.PROJECT_EXECUTION in result.signal_types


# 4 -------------------------------------------------------------------------
def test_expansion_detection():
    result = analyze(signal_description="Opening a new delivery center as part of a business expansion.")
    assert SignalType.EXPANSION in result.signal_types


# 5 -------------------------------------------------------------------------
def test_digital_transformation_detection():
    result = analyze(signal_description="A large digital transformation and cloud migration programme.")
    assert SignalType.DIGITAL_TRANSFORMATION in result.signal_types


# 6 -------------------------------------------------------------------------
def test_technology_initiative_detection():
    result = analyze(signal_description="Launching an AI initiative built on a new data platform.")
    assert SignalType.TECHNOLOGY_INITIATIVE in result.signal_types


# 7 -------------------------------------------------------------------------
def test_vendor_requirement_detection():
    result = analyze(signal_description="Seeking a staff augmentation partner for external resources.")
    assert SignalType.VENDOR_REQUIREMENT in result.signal_types


# 8 -------------------------------------------------------------------------
def test_contract_detection():
    result = analyze(signal_description="Signed a master service agreement and a statement of work.")
    assert SignalType.CONTRACT in result.signal_types


# 9 -------------------------------------------------------------------------
def test_multiple_signal_detection():
    result = analyze(
        signal_description=(
            "The company won a major banking modernization project and is hiring "
            "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
        )
    )
    expected = {SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION}
    assert expected.issubset(set(result.signal_types))
    assert result.signal_strength_label == STRONG
    assert result.signal_strength >= 80


# 10 ------------------------------------------------------------------------
def test_no_meaningful_signal():
    result = analyze(signal_description="The company posted a general administrative vacancy.")
    assert result.signal_types == [SignalType.OTHER]
    assert SignalType.HIRING not in result.signal_types
    assert result.signal_strength == 0
    assert result.signal_strength_label == WEAK


# 11 ------------------------------------------------------------------------
def test_signal_strength_boundaries():
    strong = analyze(
        signal_description=(
            "Won the contract for a digital transformation project; hiring 40 Java "
            "engineers and engaging a staff augmentation partner."
        ),
        source_name="government tender",
    )
    weak = analyze(signal_description="Company is hiring two frontend developers.")
    empty = analyze()
    for r in (strong, weak, empty):
        assert 0 <= r.signal_strength <= 100
    assert strong.signal_strength_label == STRONG
    assert weak.signal_strength < strong.signal_strength
    assert weak.signal_strength_label == WEAK
    assert empty.signal_strength == 0


# 12 ------------------------------------------------------------------------
def test_technology_extraction():
    result = analyze(
        signal_description="Stack: Java, Spring Boot, AWS, Kubernetes, Node.js, .NET and C#."
    )
    techs = set(result.detected_technologies)
    assert {"Java", "AWS", "Kubernetes", "Node.js", ".NET", "C#"}.issubset(techs)
    assert "Spring Boot" in techs
    assert "Spring" not in techs  # suppressed in favour of the specific match


def test_technology_no_false_positives():
    result = analyze(signal_description="Please email the retail team about the detail.")
    assert "AI" not in result.detected_technologies
    assert "ML" not in result.detected_technologies


# 13 ------------------------------------------------------------------------
def test_hiring_volume_extraction():
    result = analyze(signal_description="We are hiring 30 Java developers and 15 AWS engineers.")
    assert result.estimated_hiring == 45


def test_hiring_volume_none_when_unquantified():
    result = analyze(signal_description="We are hiring two frontend developers.")
    assert result.estimated_hiring is None


def test_hiring_volume_preserves_provided_value():
    result = analyze(signal_description="Growing the engineering team.", estimated_hiring=12)
    assert result.estimated_hiring == 12


# 14 ------------------------------------------------------------------------
def test_role_extraction():
    result = analyze(signal_description="Hiring 30 Java developers and 15 AWS engineers.")
    assert "Java Developer" in result.detected_roles
    assert "AWS Engineer" in result.detected_roles


# 15 ------------------------------------------------------------------------
def test_case_insensitive_matching():
    upper = analyze(signal_description="HIRING ENGINEERS")
    lower = analyze(signal_description="hiring engineers")
    assert SignalType.HIRING in upper.signal_types
    assert set(upper.signal_types) == set(lower.signal_types)


# 16 ------------------------------------------------------------------------
def test_empty_input():
    result = analyze()
    assert result.signal_types == [SignalType.OTHER]
    assert result.signal_strength == 0
    assert result.estimated_hiring is None
    assert result.detected_technologies == []
    assert result.detected_roles == []


def test_empty_input_via_model():
    result = detector.detect(SignalDetectionInput())
    assert result.signal_types == [SignalType.OTHER]


# 17 ------------------------------------------------------------------------
def test_missing_optional_fields():
    # Only a title supplied; no description/technologies/etc.
    result = analyze(signal_title="Hiring senior developers")
    assert SignalType.HIRING in result.signal_types


# 18 ------------------------------------------------------------------------
def test_duplicate_keywords_are_deduplicated():
    result = analyze(signal_description="hiring hiring hiring engineers engineers")
    assert result.signal_types.count(SignalType.HIRING) == 1
    assert result.detected_keywords.count("hiring") == 1


# §14 example cases ---------------------------------------------------------
def test_example_strong_multi_signal():
    result = analyze(
        signal_description=(
            "The company won a major banking modernization project and is hiring "
            "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
        )
    )
    assert {SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION}.issubset(
        set(result.signal_types)
    )
    assert {"Java", "AWS", "DevOps"}.issubset(set(result.detected_technologies))
    assert result.estimated_hiring == 45
    assert result.signal_strength_label == STRONG


def test_example_weak_hiring():
    result = analyze(signal_description="Company is hiring two frontend developers.")
    assert SignalType.HIRING in result.signal_types
    assert result.signal_strength_label == WEAK


def test_example_administrative_vacancy_is_not_a_tech_opportunity():
    result = analyze(signal_description="The company posted a general administrative vacancy.")
    assert result.signal_strength < 50
    assert result.detected_technologies == []


# API ergonomics + serialization -------------------------------------------
def test_detect_accepts_dict_and_convenience_wrapper():
    from_dict = detector.detect({"signal_description": "hiring engineers"})
    from_fn = run_signal_detection(signal_description="hiring engineers")
    assert SignalType.HIRING in from_dict.signal_types
    assert SignalType.HIRING in from_fn.signal_types


def test_result_serializes_enums_to_strings():
    result = analyze(signal_description="We were awarded the contract and are hiring engineers.")
    payload = result.model_dump(mode="json")
    assert "PROJECT_AWARD" in payload["signal_types"]
    assert payload["signals"][0]["signal_type"] in {s.value for s in SignalType}


def test_input_is_not_mutated():
    data = SignalDetectionInput(signal_description="hiring engineers", technologies=["Java"])
    before = data.model_copy(deep=True)
    detector.detect(data)
    assert data == before


@pytest.mark.parametrize(
    "text,expected",
    [
        ("We are recruiting developers.", SignalType.HIRING),
        ("Contract awarded to our firm.", SignalType.PROJECT_AWARD),
        ("Large data migration and integration effort.", SignalType.PROJECT_EXECUTION),
        ("Outsourcing to a technology partner.", SignalType.VENDOR_REQUIREMENT),
    ],
)
def test_representative_keywords(text, expected):
    assert expected in analyze(signal_description=text).signal_types

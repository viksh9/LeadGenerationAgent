"""Unit tests for individual normalization functions (§41 scenarios 1-20)."""

from __future__ import annotations

from datetime import datetime

import pytest

from database.models import RemoteType
from processors.normalization.company_normalizer import normalize_company, normalize_domain
from processors.normalization.date_normalizer import normalize_date
from processors.normalization.field_normalizers import (
    EmploymentType,
    SourceName,
    normalize_employment_type,
    normalize_experience,
    normalize_salary,
    normalize_source_name,
    normalize_url,
)
from processors.normalization.industry_normalizer import IndustryTaxonomy, normalize_industry
from processors.normalization.location_normalizer import normalize_location
from processors.normalization.relevance import ITRelevance, is_it_relevant_job
from processors.normalization.role_normalizer import RoleTaxonomy, normalize_role_taxonomy
from processors.normalization.technology_normalizer import (
    TechnologyCategory,
    category_of,
    normalize_technologies,
)
from processors.normalization.title_normalizer import SeniorityLevel, extract_seniority, normalize_title


# 1. Title normalization
@pytest.mark.parametrize("raw,expected", [
    ("Sr Java Developer", "Senior Java Developer"),
    ("Sr. Java Developer", "Senior Java Developer"),
    ("Java Dev", "Java Developer"),
    ("Full Stack Dev", "Full Stack Developer"),
    ("Software Engg", "Software Engineer"),
])
def test_title_normalization(raw, expected):
    assert normalize_title(raw)[0] == expected


# 2. Seniority
@pytest.mark.parametrize("raw,level", [
    ("Sr. Java Developer", SeniorityLevel.SENIOR),
    ("Senior Engineer", SeniorityLevel.SENIOR),
    ("Technical Lead", SeniorityLevel.LEAD),
    ("Engineering Manager", SeniorityLevel.MANAGER),
    ("Principal Engineer", SeniorityLevel.PRINCIPAL),
    ("Java Developer", SeniorityLevel.UNKNOWN),
    ("Software Development Engineer II", SeniorityLevel.UNKNOWN),
])
def test_seniority(raw, level):
    assert extract_seniority(raw) is level


# 3. Role taxonomy
@pytest.mark.parametrize("title,taxonomy", [
    ("Java Backend Developer", RoleTaxonomy.JAVA_ENGINEERING),
    ("Python Engineer", RoleTaxonomy.PYTHON_ENGINEERING),
    ("AWS Cloud Engineer", RoleTaxonomy.CLOUD_ENGINEERING),
    ("DevOps Specialist", RoleTaxonomy.DEVOPS_ENGINEERING),
    ("SDET", RoleTaxonomy.QA_AUTOMATION),
    ("ReactJS Developer", RoleTaxonomy.FRONTEND_ENGINEERING),
    ("Data Engineer", RoleTaxonomy.DATA_ENGINEERING),
    ("Machine Learning Engineer", RoleTaxonomy.AI_ML_ENGINEERING),
])
def test_role_taxonomy(title, taxonomy):
    assert normalize_role_taxonomy(title) is taxonomy


# 4 & 5. Technology normalization + categories
def test_technology_normalization():
    techs, cats = normalize_technologies(terms=["Java", "JAVA", "SpringBoot", "AWS", "K8s", "TS", "ReactJS"])
    assert techs == ["Java", "Spring Boot", "AWS", "Kubernetes", "TypeScript", "React"]  # deduped + canonical
    assert cats["AWS"] == "CLOUD" and cats["Kubernetes"] == "CONTAINERIZATION"


def test_technology_categories():
    assert category_of("Java") is TechnologyCategory.PROGRAMMING_LANGUAGE
    assert category_of("Kafka") is TechnologyCategory.MESSAGING
    assert category_of("Selenium") is TechnologyCategory.TESTING


def test_java_not_matched_in_javascript():
    techs, _ = normalize_technologies(text="strong JavaScript skills")
    assert "JavaScript" in techs and "Java" not in techs


# 6-9. Location
@pytest.mark.parametrize("raw,city,state", [
    ("Bangalore, Karnataka", "Bengaluru", "Karnataka"),
    ("Bengaluru", "Bengaluru", "Karnataka"),
    ("Bombay", "Mumbai", "Maharashtra"),
    ("Gurgaon", "Gurugram", "Haryana"),
    ("HITEC City, Hyderabad", "Hyderabad", "Telangana"),
])
def test_location(raw, city, state):
    loc = normalize_location(raw)
    assert loc.normalized_city == city and loc.normalized_state == state
    assert loc.normalized_country == "India"


def test_remote_type_and_region():
    assert normalize_location("Remote - India").remote_type is RemoteType.REMOTE
    assert normalize_location("Bengaluru").normalized_region == "South India"


def test_unknown_location_not_guessed():
    loc = normalize_location("Springfield")
    assert loc.normalized_city is None
    assert any("could not be mapped" in w for w in loc.warnings)


# 10-11. Company + domain
def test_company_normalization_preserves_identity():
    c = normalize_company("ABC Technologies Pvt Ltd", domain_or_url="https://www.abc.com/careers")
    assert c.original_company_name == "ABC Technologies Pvt Ltd"
    assert c.normalized_company_name == "abc technologies"   # suffix stripped, not "abc"
    assert c.company_domain == "abc.com"
    assert c.company_identity_confidence > 0


@pytest.mark.parametrize("raw,domain", [
    ("https://www.example.com/", "example.com"),
    ("http://example.com", "example.com"),
    ("www.example.com", "example.com"),
    ("example.com", "example.com"),
])
def test_domain_normalization(raw, domain):
    assert normalize_domain(raw) == domain


# 12. Industry
@pytest.mark.parametrize("raw,taxonomy", [
    ("Information Technology & Services", IndustryTaxonomy.IT_SERVICES),
    ("SaaS", IndustryTaxonomy.SAAS),
    ("Cyber Security", IndustryTaxonomy.CYBERSECURITY),
    ("IT Consulting", IndustryTaxonomy.IT_CONSULTING),
    ("Manufacturing", IndustryTaxonomy.NON_IT),
    ("", IndustryTaxonomy.UNKNOWN),
])
def test_industry(raw, taxonomy):
    assert normalize_industry(raw) is taxonomy


# 13. IT relevance
def test_it_relevance():
    assert is_it_relevant_job(title="Senior Java Engineer", technologies=["Java", "AWS"],
                              role_taxonomy=RoleTaxonomy.JAVA_ENGINEERING) is ITRelevance.HIGH
    assert is_it_relevant_job(title="Warehouse Manager", technologies=[],
                              role_taxonomy=RoleTaxonomy.OTHER) is ITRelevance.LOW


# 14. Employment type
@pytest.mark.parametrize("raw,etype", [
    ("Full Time", EmploymentType.FULL_TIME),
    ("Permanent", EmploymentType.FULL_TIME),
    ("Contract", EmploymentType.CONTRACT),
    ("Internship", EmploymentType.INTERNSHIP),
    ("", EmploymentType.UNKNOWN),
])
def test_employment_type(raw, etype):
    assert normalize_employment_type(raw) is etype


# 15. Experience
def test_experience():
    assert normalize_experience("5-8 years") == (5, 8)
    assert normalize_experience("5+ years") == (5, None)
    assert normalize_experience("Experienced professional") == (None, None)


# 16. Salary
def test_salary():
    assert normalize_salary("10 LPA")[:4] == (1_000_000, None, "INR", "ANNUAL")
    lo, hi, cur, period, _ = normalize_salary("INR 12-18 LPA")
    assert (lo, hi, cur, period) == (1_200_000, 1_800_000, "INR", "ANNUAL")


# 17. Date
def test_date():
    now = datetime(2026, 9, 5)
    assert normalize_date("2026-09-03")[0] == datetime(2026, 9, 3)
    assert normalize_date("2 days ago", now=now)[0] == datetime(2026, 9, 3)
    assert normalize_date("yesterday", now=now)[0] == datetime(2026, 9, 4)
    assert normalize_date("25/12/2026")[0] == datetime(2026, 12, 25)
    assert normalize_date("garbage")[0] is None


# 18. Source
@pytest.mark.parametrize("raw,name", [
    ("LinkedIn Jobs", SourceName.LINKEDIN),
    ("adzuna", SourceName.ADZUNA),
    ("company_career_pages", SourceName.COMPANY_CAREER),
    ("something else", SourceName.OTHER),
])
def test_source_name(raw, name):
    assert normalize_source_name(raw) is name


# 19. URL
def test_url_normalization():
    norm, _ = normalize_url("https://ex.com/jobs/1/?utm_source=x&id=5#frag")
    assert norm == "https://ex.com/jobs/1?id=5"


# 20. Multi-value
def test_multi_value_dedup():
    techs, _ = normalize_technologies(terms=["Java", "java", "JAVA"])
    assert techs == ["Java"]

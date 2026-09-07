"""Technology normalization: aliases -> canonical name + category.

Configurable taxonomy. Word-boundary matching prevents partials ("java" never
matches inside "javascript"). Original technology terms are preserved by the
caller; this only produces the normalized set + categories. Unrelated
technologies are never merged.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable, Optional


class TechnologyCategory(str, Enum):
    PROGRAMMING_LANGUAGE = "PROGRAMMING_LANGUAGE"
    FRAMEWORK = "FRAMEWORK"
    DATABASE = "DATABASE"
    CLOUD = "CLOUD"
    DEVOPS = "DEVOPS"
    CONTAINERIZATION = "CONTAINERIZATION"
    MESSAGING = "MESSAGING"
    DATA = "DATA"
    AI_ML = "AI_ML"
    TESTING = "TESTING"
    SECURITY = "SECURITY"
    MOBILE = "MOBILE"
    ERP = "ERP"
    CRM = "CRM"
    BI = "BI"
    OTHER = "OTHER"


# canonical -> (aliases, category). Configurable.
TECHNOLOGY_TAXONOMY: dict[str, tuple[tuple[str, ...], TechnologyCategory]] = {
    "Java": (("java", "jdk", "core java", "java 8", "java 11", "java 17"), TechnologyCategory.PROGRAMMING_LANGUAGE),
    "Python": (("python",), TechnologyCategory.PROGRAMMING_LANGUAGE),
    "JavaScript": (("javascript", "java script", "js", "ecmascript"), TechnologyCategory.PROGRAMMING_LANGUAGE),
    "TypeScript": (("typescript", "type script", "ts"), TechnologyCategory.PROGRAMMING_LANGUAGE),
    "C#": (("c#", "c sharp", "csharp"), TechnologyCategory.PROGRAMMING_LANGUAGE),
    ".NET": ((".net", "dotnet", "dot net", ".net core", "asp.net"), TechnologyCategory.FRAMEWORK),
    "Spring Boot": (("spring boot", "springboot"), TechnologyCategory.FRAMEWORK),
    "Spring": (("spring",), TechnologyCategory.FRAMEWORK),
    "React": (("react", "react.js", "reactjs", "react js"), TechnologyCategory.FRAMEWORK),
    "Angular": (("angular", "angularjs"), TechnologyCategory.FRAMEWORK),
    "Node.js": (("node.js", "nodejs", "node js", "node"), TechnologyCategory.FRAMEWORK),
    "Django": (("django",), TechnologyCategory.FRAMEWORK),
    "AWS": (("aws", "amazon web services"), TechnologyCategory.CLOUD),
    "Azure": (("azure", "microsoft azure"), TechnologyCategory.CLOUD),
    "GCP": (("gcp", "google cloud platform", "google cloud"), TechnologyCategory.CLOUD),
    "Kubernetes": (("kubernetes", "k8s"), TechnologyCategory.CONTAINERIZATION),
    "Docker": (("docker",), TechnologyCategory.CONTAINERIZATION),
    "DevOps": (("devops",), TechnologyCategory.DEVOPS),
    "Terraform": (("terraform",), TechnologyCategory.DEVOPS),
    "Kafka": (("kafka", "apache kafka"), TechnologyCategory.MESSAGING),
    "SQL": (("sql",), TechnologyCategory.DATABASE),
    "PostgreSQL": (("postgresql", "postgres", "psql"), TechnologyCategory.DATABASE),
    "MySQL": (("mysql",), TechnologyCategory.DATABASE),
    "MongoDB": (("mongodb", "mongo db", "mongo"), TechnologyCategory.DATABASE),
    "Redis": (("redis",), TechnologyCategory.DATABASE),
    "Selenium": (("selenium",), TechnologyCategory.TESTING),
    "Playwright": (("playwright",), TechnologyCategory.TESTING),
    "AI": (("artificial intelligence", "ai"), TechnologyCategory.AI_ML),
    "Machine Learning": (("machine learning", "ml"), TechnologyCategory.AI_ML),
    "Generative AI": (("generative ai", "gen ai", "genai"), TechnologyCategory.AI_ML),
    "Data Engineering": (("data engineering",), TechnologyCategory.DATA),
    "Spark": (("apache spark", "spark"), TechnologyCategory.DATA),
    "SAP": (("sap",), TechnologyCategory.ERP),
    "Salesforce": (("salesforce",), TechnologyCategory.CRM),
    "ServiceNow": (("servicenow", "service now"), TechnologyCategory.OTHER),
    "Power BI": (("power bi", "powerbi"), TechnologyCategory.BI),
    "Tableau": (("tableau",), TechnologyCategory.BI),
    "Cybersecurity": (("cybersecurity", "cyber security", "infosec"), TechnologyCategory.SECURITY),
    "Android": (("android",), TechnologyCategory.MOBILE),
    "iOS": (("ios",), TechnologyCategory.MOBILE),
}

# Suppress the less-specific canonical when the more-specific one is present.
_SUPPRESS = {"Spring Boot": "Spring"}

_ALIAS_TO_CANONICAL: list[tuple[str, str]] = sorted(
    ((alias, canonical) for canonical, (aliases, _) in TECHNOLOGY_TAXONOMY.items() for alias in aliases),
    key=lambda t: -len(t[0]),
)
_PATTERN = re.compile(
    r"(?<![\w.#])(" + "|".join(re.escape(a) for a, _ in _ALIAS_TO_CANONICAL) + r")(?![\w])",
    re.IGNORECASE,
)
_LOOKUP = {alias.lower(): canonical for alias, canonical in _ALIAS_TO_CANONICAL}


def category_of(canonical: str) -> TechnologyCategory:
    entry = TECHNOLOGY_TAXONOMY.get(canonical)
    return entry[1] if entry else TechnologyCategory.OTHER


def normalize_technology_term(term: Optional[str]) -> Optional[str]:
    """Normalize a single source term to its canonical name (or None)."""
    if not term:
        return None
    found = extract_technologies_normalized(term)
    return found[0] if found else None


def extract_technologies_normalized(text: Optional[str]) -> list[str]:
    """Canonical technologies present in `text`, de-duplicated + order-stable."""
    if not text:
        return []
    found: list[str] = []
    for m in _PATTERN.finditer(text):
        canonical = _LOOKUP.get(m.group(1).lower())
        if canonical and canonical not in found:
            found.append(canonical)
    for specific, less in _SUPPRESS.items():
        if specific in found and less in found:
            found.remove(less)
    return found


def normalize_technologies(*, text: Optional[str] = None, terms: Optional[Iterable[str]] = None) -> tuple[list[str], dict[str, str]]:
    """Return (normalized_technologies, {canonical: category}) from free text
    and/or an explicit list of source terms (multi-value normalized + deduped)."""
    canon: list[str] = []
    if text:
        canon.extend(extract_technologies_normalized(text))
    for term in terms or []:
        c = normalize_technology_term(term)
        if c and c not in canon:
            canon.append(c)
    # De-dup while preserving order (multi-value normalization).
    seen: set[str] = set()
    unique = [c for c in canon if not (c in seen or seen.add(c))]
    categories = {c: category_of(c).value for c in unique}
    return unique, categories

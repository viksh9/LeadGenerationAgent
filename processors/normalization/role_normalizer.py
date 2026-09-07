"""Role taxonomy normalization.

Maps a job title onto a configurable, coarse role taxonomy (JAVA_ENGINEERING,
CLOUD_ENGINEERING, …) for grouping/analytics. Language-specific roles win over
generic ones (per the spec: "Java Backend Developer" -> JAVA_ENGINEERING). The
human-readable normalized_role (display) is produced separately by
ingestion.extract.normalize_role.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class RoleTaxonomy(str, Enum):
    QA_AUTOMATION = "QA_AUTOMATION"
    AI_ML_ENGINEERING = "AI_ML_ENGINEERING"
    DATA_SCIENCE = "DATA_SCIENCE"
    DATA_ENGINEERING = "DATA_ENGINEERING"
    CLOUD_ENGINEERING = "CLOUD_ENGINEERING"
    DEVOPS_ENGINEERING = "DEVOPS_ENGINEERING"
    SRE = "SRE"
    SECURITY_ENGINEERING = "SECURITY_ENGINEERING"
    MOBILE_ENGINEERING = "MOBILE_ENGINEERING"
    FRONTEND_ENGINEERING = "FRONTEND_ENGINEERING"
    JAVA_ENGINEERING = "JAVA_ENGINEERING"
    PYTHON_ENGINEERING = "PYTHON_ENGINEERING"
    DOTNET_ENGINEERING = "DOTNET_ENGINEERING"
    BACKEND_ENGINEERING = "BACKEND_ENGINEERING"
    FULLSTACK_ENGINEERING = "FULLSTACK_ENGINEERING"
    ARCHITECTURE = "ARCHITECTURE"
    ENGINEERING_MANAGEMENT = "ENGINEERING_MANAGEMENT"
    PROGRAM_MANAGEMENT = "PROGRAM_MANAGEMENT"
    SOFTWARE_ENGINEERING = "SOFTWARE_ENGINEERING"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


# Ordered rules (most specific first). Configurable.
_RULES: tuple[tuple[RoleTaxonomy, tuple[str, ...]], ...] = (
    (RoleTaxonomy.QA_AUTOMATION, ("sdet", "qa automation", "automation test", "test automation",
                                  "automation engineer", "automation specialist", "automation tester", "qa engineer")),
    (RoleTaxonomy.AI_ML_ENGINEERING, ("machine learning", "ml engineer", "mlops", "ai engineer",
                                      "generative ai", "gen ai", "genai", "deep learning")),
    (RoleTaxonomy.DATA_SCIENCE, ("data scientist", "data science")),
    (RoleTaxonomy.DATA_ENGINEERING, ("data engineer", "big data", "data platform", "etl developer")),
    (RoleTaxonomy.CLOUD_ENGINEERING, ("cloud engineer", "aws engineer", "azure engineer", "gcp engineer",
                                      "aws cloud", "cloud architect", "cloud")),
    (RoleTaxonomy.DEVOPS_ENGINEERING, ("devops", "platform engineer")),
    (RoleTaxonomy.SRE, ("site reliability", "sre")),
    (RoleTaxonomy.SECURITY_ENGINEERING, ("security engineer", "cybersecurity", "cyber security", "infosec")),
    (RoleTaxonomy.MOBILE_ENGINEERING, ("android", "ios developer", "mobile developer", "mobile engineer")),
    (RoleTaxonomy.FRONTEND_ENGINEERING, ("react", "angular", "frontend", "front-end", "front end", "ui developer")),
    (RoleTaxonomy.JAVA_ENGINEERING, ("java",)),
    (RoleTaxonomy.PYTHON_ENGINEERING, ("python",)),
    (RoleTaxonomy.DOTNET_ENGINEERING, (".net", "dotnet", "c#", "c sharp")),
    (RoleTaxonomy.BACKEND_ENGINEERING, ("backend", "back-end", "back end")),
    (RoleTaxonomy.FULLSTACK_ENGINEERING, ("full stack", "fullstack", "full-stack")),
    (RoleTaxonomy.ARCHITECTURE, ("architect",)),
    (RoleTaxonomy.ENGINEERING_MANAGEMENT, ("engineering manager", "development manager", "delivery manager")),
    (RoleTaxonomy.PROGRAM_MANAGEMENT, ("program manager", "delivery lead", "project manager", "scrum master")),
    (RoleTaxonomy.SOFTWARE_ENGINEERING, ("software engineer", "software developer", "software development engineer",
                                         "sde", "developer", "engineer")),
)


def normalize_role_taxonomy(title: Optional[str], description: Optional[str] = None) -> RoleTaxonomy:
    if not title and not description:
        return RoleTaxonomy.UNKNOWN
    text = " ".join(p for p in (title, description) if p).lower()
    for taxonomy, cues in _RULES:
        if any(c in text for c in cues):
            return taxonomy
    return RoleTaxonomy.OTHER

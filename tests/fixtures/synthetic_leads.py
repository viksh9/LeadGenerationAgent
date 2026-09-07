"""Reusable SYNTHETIC lead builders for tests.

Each builder returns a raw lead dict (LeadAnalyzeRequest fields + a relative
`signal_age_days`) shaped exactly like tests/fixtures/sample_leads.json. All data
is synthetic — role-only POCs, fictional companies, no real personal data.
"""

from __future__ import annotations

from typing import Any


def hot_lead(**overrides: Any) -> dict:
    """Recent project award + large tech hiring -> HOT."""
    base = {
        "company_name": "NorthWind Digital Labs",
        "industry": "IT",
        "location": "Bengaluru",
        "signal_title": "Large engineering ramp-up for awarded project",
        "signal_description": "NorthWind won a project awarded by a bank and is hiring 40 Java, Spring Boot and AWS engineers.",
        "source_name": "Synthetic Company Announcement",
        "source_url": "https://synthetic.example/northwind/ramp",
        "technologies": ["Java", "Spring Boot", "AWS"],
        "project_name": "Digital Banking Modernization",
        "project_value": 25000000,
        "estimated_hiring": 40,
        "hiring_roles": ["Java Engineer", "AWS Engineer"],
        "company_size": "1001-5000",
        "poc_title": "VP of Engineering",
        "signal_confidence": 92,
        "signal_age_days": 2,
    }
    return {**base, **overrides}


def warm_lead(**overrides: Any) -> dict:
    """Digital transformation + moderate hiring -> WARM."""
    base = {
        "company_name": "BluePeak Systems",
        "industry": "BFSI",
        "location": "Mumbai",
        "signal_title": "Digital transformation program",
        "signal_description": "BluePeak launched a digital transformation and cloud migration program, hiring 12 Java and AWS engineers.",
        "source_name": "Synthetic Business News",
        "source_url": "https://synthetic.example/bluepeak/dx",
        "technologies": ["Java", "AWS", "Kubernetes"],
        "estimated_hiring": 12,
        "hiring_roles": ["Cloud Engineer", "DevOps Engineer"],
        "poc_title": "CTO",
        "signal_confidence": 74,
        "signal_age_days": 18,
    }
    return {**base, **overrides}


def nurture_lead(**overrides: Any) -> dict:
    """Small hiring, older signal -> NURTURE."""
    base = {
        "company_name": "GreenBasket Tech",
        "industry": "FMCG",
        "location": "Gurugram",
        "signal_title": "Small backend hiring",
        "signal_description": "GreenBasket is hiring 5 Python developers.",
        "source_name": "Synthetic Job Portal",
        "source_url": "https://synthetic.example/greenbasket/py",
        "technologies": ["Python"],
        "estimated_hiring": 5,
        "hiring_roles": ["Python Developer"],
        "poc_title": "Talent Acquisition Head",
        "signal_confidence": 50,
        "signal_age_days": 45,
    }
    return {**base, **overrides}


def low_lead(**overrides: Any) -> dict:
    """Weak/general signal, no tech, old -> LOW."""
    base = {
        "company_name": "HealthBridge Care",
        "industry": "Healthcare",
        "location": "Hyderabad",
        "signal_title": "General company update",
        "signal_description": "HealthBridge published a general company update.",
        "technologies": [],
        "hiring_roles": [],
        "signal_confidence": 18,
        "signal_age_days": 120,
    }
    return {**base, **overrides}


def project_lead(**overrides: Any) -> dict:
    """Project award signal."""
    base = {
        "company_name": "RetailOrbit Tech",
        "industry": "IT",
        "location": "Gurugram",
        "signal_title": "Contract awarded for platform",
        "signal_description": "RetailOrbit won contract and was awarded a platform project; hiring 20 Java engineers.",
        "source_name": "Synthetic Government Tender",
        "source_url": "https://synthetic.example/retailorbit/won",
        "technologies": ["Java", "Angular"],
        "project_name": "Citizen Services Platform",
        "project_value": 30000000,
        "estimated_hiring": 20,
        "hiring_roles": ["Java Engineer"],
        "poc_title": "CIO",
        "signal_confidence": 90,
        "signal_age_days": 3,
    }
    return {**base, **overrides}


def hiring_lead(**overrides: Any) -> dict:
    """Pure hiring signal."""
    base = {
        "company_name": "CloudNova Labs",
        "industry": "IT",
        "location": "Pune",
        "signal_title": "Hiring DevOps engineers",
        "signal_description": "CloudNova is hiring 10 DevOps and Kubernetes engineers.",
        "source_name": "Synthetic Career Page",
        "source_url": "https://synthetic.example/cloudnova/devops",
        "technologies": ["DevOps", "Kubernetes", "Docker"],
        "estimated_hiring": 10,
        "hiring_roles": ["DevOps Engineer", "Platform Engineer"],
        "poc_title": "Head of Engineering",
        "signal_confidence": 66,
        "signal_age_days": 10,
    }
    return {**base, **overrides}


def vendor_lead(**overrides: Any) -> dict:
    """Vendor / staff augmentation signal."""
    base = {
        "company_name": "SilverLine Financial",
        "industry": "BFSI",
        "location": "Pune",
        "signal_title": "Vendor requirement for staff augmentation",
        "signal_description": "SilverLine has a vendor requirement and needs staff augmentation and external resources.",
        "source_name": "Synthetic Project Registry",
        "source_url": "https://synthetic.example/silverline/vendor",
        "technologies": [".NET", "Azure"],
        "hiring_roles": [],
        "poc_title": "IT Sourcing Manager",
        "signal_confidence": 60,
        "signal_age_days": 20,
    }
    return {**base, **overrides}


def digital_transformation_lead(**overrides: Any) -> dict:
    """Digital transformation signal."""
    base = {
        "company_name": "PrimeCare Digital",
        "industry": "Healthcare",
        "location": "Chennai",
        "signal_title": "Cloud modernization initiative",
        "signal_description": "PrimeCare began a digital transformation and cloud modernization of legacy systems.",
        "source_name": "Synthetic Business News",
        "source_url": "https://synthetic.example/primecare/dx",
        "technologies": ["GCP", "Kubernetes"],
        "estimated_hiring": 14,
        "hiring_roles": ["Cloud Engineer"],
        "poc_title": "Program Director",
        "signal_confidence": 72,
        "signal_age_days": 25,
    }
    return {**base, **overrides}


def missing_data_lead(**overrides: Any) -> dict:
    """Minimal lead: company only, no POC/source/tech/project."""
    base = {
        "company_name": "Sparse Signals Inc",
        "industry": "IT",
        "signal_title": "Unconfirmed technology interest",
        "signal_description": "Sparse Signals may explore technology work.",
        "technologies": [],
        "hiring_roles": [],
        "signal_confidence": 12,
        "signal_age_days": 90,
    }
    return {**base, **overrides}


ALL_BUILDERS = {
    "hot": hot_lead,
    "warm": warm_lead,
    "nurture": nurture_lead,
    "low": low_lead,
    "project": project_lead,
    "hiring": hiring_lead,
    "vendor": vendor_lead,
    "digital": digital_transformation_lead,
    "missing": missing_data_lead,
}

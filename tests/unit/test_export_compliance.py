"""Export real-data compliance scanner (Prompt 55, §24). Pure — no DB."""

from __future__ import annotations

from export.compliance import scan_rows


def _row(**kw):
    base = {"Company Name": "Infosys Ltd", "Source": "Official Career Site", "Business Email": None}
    base.update(kw)
    return base


def test_clean_real_rows_pass():
    report = scan_rows([_row(), _row(**{"Company Name": "Tata Consultancy Services"})])
    assert report.ok
    assert report.rows_scanned == 2


def test_detects_example_domain():
    report = scan_rows([_row(**{"Business Email": "ceo@example.com"})])
    assert not report.ok
    assert any(v.kind == "demo-marker" and "example-domain" in v.detail for v in report.violations)


def test_detects_john_doe():
    report = scan_rows([_row(**{"Target POC": "John Doe"})])
    assert any("john-doe" in v.detail for v in report.violations)


def test_detects_test_company_phrase():
    report = scan_rows([_row(**{"Company Name": "Test Company Pvt"})])
    assert any("test-company" in v.detail for v in report.violations)


def test_does_not_flag_legit_names_containing_substrings():
    # Real Indian companies whose names merely contain 'test'/'sample'/'demo' fragments.
    rows = [_row(**{"Company Name": "Testbook Edu Solutions"}),
            _row(**{"Company Name": "Sampleboard Technologies"}),
            _row(**{"Company Name": "Democratic Systems India"})]
    report = scan_rows(rows)
    assert report.ok, [v.detail for v in report.violations]


def test_detects_sequential_and_zero_phone():
    r1 = scan_rows([_row(**{"Business Phone": "1234567890"})])
    r2 = scan_rows([_row(**{"Business Phone": "0000000000"})])
    assert not r1.ok and not r2.ok


def test_missing_provenance_flagged():
    report = scan_rows([{"Company Name": "Infosys Ltd", "Source": "", "Source URL": "", "Supporting Sources": ""}])
    assert any(v.kind == "missing-provenance" for v in report.violations)


def test_provenance_ok_when_any_source_field_present():
    report = scan_rows([{"Company Name": "Infosys Ltd", "Source": "", "Source URL": "",
                         "Supporting Sources": "GitHub"}])
    assert report.ok

"""Excel export of REAL data (Prompt 45).

Exports only the actual business records currently stored in the application
database — all source-traceable, provenance-preserving. Never fabricates rows;
never exports secrets. Formula-injection is neutralised on all text cells.
"""

from export.excel import build_workbook, workbook_counts

__all__ = ["build_workbook", "workbook_counts"]

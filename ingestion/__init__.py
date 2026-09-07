"""Raw-to-lead ingestion: normalize RawSourceRecords into analyzed Leads.

This layer sits between the raw ingestion layer (collectors -> raw_source_records)
and the intelligence engines (signal detection -> scoring). It normalizes a raw
record into a LeadAnalyzeRequest and runs the existing LeadAnalysisPipeline.
"""

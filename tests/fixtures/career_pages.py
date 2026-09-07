"""Synthetic career-page fixtures for offline parser/collector tests.

All content is fabricated (example.com/example domains). No real company data.
"""

from __future__ import annotations

# 1. JSON-LD JobPosting — full IT job with salary + date + location.
JSONLD_SINGLE = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Senior Java Developer",
  "description": "Build microservices with Java, Spring Boot and AWS. Kubernetes a plus.",
  "datePosted": "2026-08-15",
  "validThrough": "2026-10-15",
  "employmentType": "FULL_TIME",
  "hiringOrganization": {"@type": "Organization", "name": "Globex Tech", "sameAs": "https://globex.example"},
  "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress",
     "addressLocality": "Bengaluru", "addressRegion": "KA", "addressCountry": "IN"}},
  "baseSalary": {"@type": "MonetaryAmount", "currency": "INR",
     "value": {"@type": "QuantitativeValue", "minValue": 1500000, "maxValue": 2500000, "unitText": "YEAR"}},
  "url": "/jobs/senior-java-developer",
  "identifier": {"@type": "PropertyValue", "value": "REQ-101"}
}
</script></head><body>Careers</body></html>
"""

# 2. JSON-LD in @graph, missing salary, IT job.
JSONLD_GRAPH = """
<html><body>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"Example Careers"},
  {"@type":"JobPosting","title":"Python Data Engineer","description":"Python, SQL and data pipelines.",
   "datePosted":"2026-08-20","hiringOrganization":{"name":"Initech"},
   "jobLocation":{"address":{"addressLocality":"Pune","addressCountry":"IN"}},
   "url":"/jobs/python-data-engineer","identifier":"REQ-202"}
]}
</script></body></html>
"""

# 3. Remote IT job (TELECOMMUTE), no date.
JSONLD_REMOTE = """
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"DevOps Engineer",
 "description":"Remote DevOps role. Docker, Kubernetes, Terraform.",
 "jobLocationType":"TELECOMMUTE","hiringOrganization":{"name":"Acme Cloud"},
 "url":"https://acme.example/jobs/devops","identifier":"D-1"}
</script>
"""

# 4. Hybrid IT job.
JSONLD_HYBRID = """
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Full Stack Engineer",
 "description":"Hybrid role in office 3 days. React and Node.js.",
 "datePosted":"2026-08-01","hiringOrganization":{"name":"Umbrella Soft"},
 "jobLocation":{"address":{"addressLocality":"Hyderabad","addressCountry":"IN"}},
 "url":"https://umbrella.example/jobs/fse","identifier":"U-9"}
</script>
"""

# 5. Non-IT job (should still be mapped, tagged NOT_RELEVANT).
JSONLD_NONIT = """
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Front Desk Receptionist",
 "description":"Greet visitors and manage the front desk.","datePosted":"2026-08-10",
 "hiringOrganization":{"name":"Globex Tech"},"url":"/jobs/receptionist","identifier":"R-1"}
</script>
"""

# 6. Embedded application/json with a jobs array.
EMBEDDED_JSON = """
<html><body>
<script type="application/json">
{"props":{"jobs":[
  {"title":"Backend Engineer","absolute_url":"https://boards.example/jobs/be-1","id":"be-1",
   "location":{"name":"Chennai"},"description":"Java and Spring backend."},
  {"jobTitle":"QA Automation Engineer","url":"/jobs/qa-1","id":42,"description":"Selenium and Python."}
]}}
</script></body></html>
"""

# 7. Plain HTML anchors (last-resort parser).
HTML_ANCHORS = """
<html><body><ul>
  <li><a href="/careers/jobs/cloud-engineer">Cloud Engineer</a></li>
  <li><a href="/careers/jobs/sre">Site Reliability Engineer</a></li>
  <li><a href="/about">About us</a></li>
</ul></body></html>
"""

# 8/9. Multi-page listing: page 1 (2 JSON-LD jobs) + rel=next; page 2 (1 job).
LISTING_PAGE1 = """
<html><head>
<link rel="next" href="/careers?page=2">
<script type="application/ld+json">
[
 {"@type":"JobPosting","title":"Java Developer","description":"Java, Spring.","datePosted":"2026-08-18",
  "hiringOrganization":{"name":"Globex Tech"},"url":"/jobs/java-dev","identifier":"P1-1"},
 {"@type":"JobPosting","title":"React Developer","description":"React, TypeScript.","datePosted":"2026-08-19",
  "hiringOrganization":{"name":"Globex Tech"},"url":"/jobs/react-dev","identifier":"P1-2"}
]
</script></head><body>page1</body></html>
"""

LISTING_PAGE2 = """
<html><head>
<script type="application/ld+json">
{"@type":"JobPosting","title":"Platform Engineer","description":"Kubernetes, AWS.","datePosted":"2026-08-21",
 "hiringOrganization":{"name":"Globex Tech"},"url":"/jobs/platform-eng","identifier":"P2-1"}
</script></head><body>page2</body></html>
"""

# 10. Malformed HTML that still contains a valid JSON-LD block.
MALFORMED = """
<html><body><div><p>Unclosed tags <b>bold
<script type="application/ld+json">
{"@type":"JobPosting","title":"AI Engineer","description":"Machine learning and Python.",
 "hiringOrganization":{"name":"Cyberdyne"},"url":"/jobs/ai-eng","identifier":"M-1"}
</script>
<span>more <a href="/jobs/ai-eng">AI Engineer</a>
</body>
"""

# 11. Missing salary AND missing date (structured but sparse).
JSONLD_SPARSE = """
<script type="application/ld+json">
{"@type":"JobPosting","title":"SDET","description":"Test automation with Playwright.",
 "hiringOrganization":{"name":"Stark Industries"},"url":"/jobs/sdet"}
</script>
"""

# 12. Duplicate job (same identifier twice in one listing).
JSONLD_DUPLICATE = """
<script type="application/ld+json">
[
 {"@type":"JobPosting","title":"Node.js Developer","description":"Node.js.","hiringOrganization":{"name":"Hooli"},
  "url":"/jobs/node-dev","identifier":"DUP-1"},
 {"@type":"JobPosting","title":"Node.js Developer","description":"Node.js.","hiringOrganization":{"name":"Hooli"},
  "url":"/jobs/node-dev","identifier":"DUP-1"}
]
</script>
"""

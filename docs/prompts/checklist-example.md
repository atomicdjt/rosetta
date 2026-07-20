Generate an inspection-ready SDLC checklist for: documentation management system for imaging, patient visits, with audio recoding and automatic transcription.

Before writing the checklist:
1. Identify the real governing standard or authority that "passing inspection" implies
   in this domain (e.g., DO-178C/NASA NPR for aerospace software, HACCP for food
   safety, SOC 2/ISO 27001 for security, GxP/21 CFR Part 11 for pharma, SOX/GAAP for
   financial controls, PCI-DSS for payments). Name it explicitly. If none formally
   exists, name the closest real-world professional practice and say so.
2. State the criticality/severity level of THIS specific task within that standard
   (e.g., DAL A vs D, Class A vs C) — rigor scales with consequence of failure, not
   with how the task feels.
3. Identify the actual failure modes at stake (what breaks, who's harmed, what's
   irreversible) — let these drive which items are severity ≥ medium.

Then produce the checklist:
- Organize by the domain's real lifecycle phases (don't force-fit generic
  "plan/build/test/deploy" if the domain has its own established stages).
- Include every item at severity ≥ medium. Do NOT cap items per section by count —
  cut only genuinely low-severity/cosmetic items, and say what you cut and why.
- Every item must be independently verifiable/falsifiable — an auditor could check
  it against evidence. Reject vague items ("follow best practices," "ensure
  quality") — restate as a checkable condition.
- Explicitly include the structural markers of real rigor, adapted to this domain:
  - Independence (reviewer/verifier/auditor ≠ author/builder)
  - Traceability (requirement/spec ↔ implementation ↔ evidence, gap-free,
    bidirectional)
  - Root-cause-driven requirements (derived from actual hazard/risk/failure
    analysis, not asserted from experience)
  - Exception handling (every waiver/deviation individually justified and signed
    off, none bundled or silently accepted)
  - Evidence of closure (a checked box requires proof, not a claim)
- Flag anything that would be a hard fail vs. a finding/observation in a real audit.

Output as a checklist, one line per item, phase-grouped headers, no padding.
# Rosetta Security Skill — Proposal

## Preface

We are already in the era of AI automated cybersecurity war without any doubt: malicious attackers without extensive training can now use already existing OSS models, Mythos, non-released GPT models to identify and use 0-day software vulnerabilities.

The clearest evidence is the response of the people who build these models. Anthropic withheld Mythos Preview from public release and gated it to roughly fifty vetted partners for defensive use only; its first publicly available successor was disabled under government pressure once its cyber capabilities were confirmed. Capabilities are not restrained this way unless they work. If the current generation of defensive tooling neutralized what these models find, none of that would be necessary.

## Problem

The asymmetry is structural: an attacker needs a single exploitable issue, while the defending team must close every one of them. AI collapses the attacker's cost of finding that one issue, so an imbalance that always favored offense now favors it decisively — and this is no longer theoretical. A criminal group has already used a model to find a zero-day and write its exploit; frontier agents have autonomously chained discovery, escape, and intrusion against live infrastructure without human direction.

Our clients are behind. It is not uncommon to see known-vulnerable packages running in production. The existing tools are not useless — each still produces valuable signal — but they operate in isolation: one scanner per concern, one repository per run, separate outputs, no shared context, and shallow or absent remediation. Nothing consumes all of that signal together, against the full picture of the system, and acts on it. Across the industry, detection was never the bottleneck; remediation is. That gap is where the one issue that matters gets through.

Defense that depends on a single central team cannot scale to meet an attacker whose cost of finding issues is now near zero. The volume of AI-discovered issues will not wait in a queue. Effort has to fan out to match, or the battle is lost by arithmetic alone.

## Proposal

Rosetta already has what those tools lack: the full context — IaC, backend, frontend — assembled as a single composite workspace across multiple repositories, the ability to run tools, and the ability to fix issues reliably. The security skill builds on that.

Four properties separate this from adding another scanner:

- **One unified view.** Every tool's output is normalized into a single finding schema, deduplicated, and prioritized. The existing scanners keep doing what they are good at; the skill reacts to and cross-checks all of their signals at once, against the whole system, rather than leaving a dozen disconnected reports for a human to reconcile.
- **Shift-left security.** Teams are capable of doing this work themselves and early.
- **Whole-solution context.** The composite workspace gives a clear view of the entire system rather than fragments, so trust-boundary and cross-repository issues become visible.
- **Grouped, systemic remediation.** The same root issue appearing in many places is fixed once, at the root, through Rosetta's coding-flow — not patched location by location. This is where the industry bottleneck actually sits, and it is Rosetta's strength.
- **Every team, in parallel.** Because the skill ships as part of Rosetta, every team already using Rosetta can run it against their own systems and fix their own issues. Defensive effort fans out across the whole organization at once instead of queuing behind one security team — the only way the volume of AI-discovered issues gets closed in time.

The skill defines the common goal, protocol, process, subagents, and orchestration; the assets define the tools, how their output is handled, and the problem areas to inspect. The skill uses the tools present in the environment — we come, recommend, and use what we are given. Where a reference exists we build on it rather than reinvent: Visa's open harness for running Mythos-class models covers discovery through validated fix, and we extend that pattern with whole-solution context and grouped remediation.

Orchestration is deliberate about sequence. Passes run in a defined order and each stage receives only what it needs — sensitive values are identified and masked before anything else reads the code, and their handling is routed separately through the coding-flow. Reports and run statistics are both retained in the repository, which makes baseline and diff comparison across runs possible. Noise and prioritization are owned by a dedicated prioritizer subagent rather than left implicit.

## Operating model

The skill runs where the code already lives — inside the client's own infrastructure, using the client's own tools (their Claude Code, their gateways) under their own authorization. It is delivered together with a trained engineer who onboards the client's team to run it themselves, so the capability stays with the client.

---

## Core protocol
1. AUTHORIZE — confirm the user owns / may test the target. Offensive areas
   (pen-test, DNS/recon, exfil, network) are HARD-GATED behind explicit,
   per-run scope confirmation. Default = defensive/static only.
2. DETECT context — languages, package managers, IaC, Dockerfiles, k8s
   manifests, cloud provider, presence of APIs. This decides which assets/*.md apply.
3. THREAT-MODEL FIRST — before scanning, build a light attack-surface + trust-
   boundary model so scanning is focused, not blind.
4. SELECT tools — from each applicable assets/*.md, pick the default fast pass
   (prefer one broad tool, e.g. Trivy, before many narrow ones).
5. RUN read-only by default — never mutate source unless user opts into fix mode.
6. NORMALIZE — every tool's output → common finding schema (see below).
7. VERIFY / DEDUP — collapse overlaps, drop likely false positives via a second
   pass or multi-signal agreement.
8. REPORT — severity-ranked, one artifact, with remediation per finding.

## Subagents / orchestration
- orchestrator — runs the protocol, owns gating + tool selection.
- area-runner (one per applicable asset) — invokes tools, captures raw output.
- normalizer — maps raw tool output → finding schema.
- triager — dedup, FP-reduction, severity ranking.   [VVAH: multi-agent voting reduces FPs]
- (optional, fix mode) remediator — proposes minimal patch per finding;
  never auto-merges; validator subagent re-checks the patch read-only. [VVAH S10–S11]
- (optional, active) pentester — white-hat ethical hacking against **pre-production only**;
  HARD-GATED behind explicit scope + ownership confirmation; chains active DAST/API/network
  tools (ZAP, Nuclei, Schemathesis, nmap) to validate that findings are actually exploitable;
  never runs against production; feeds confirmed exploit chains back to the triager for
  severity uplift and to the remediator for a fix.

## Severity of running, not just findings
Gate tools by blast radius: static/local = auto; network/active/offensive =
require typed confirmation of scope + ownership.

---

### `assets/security-architecture.md` — architectural flaws
- **Subagent Review** (adhoc subagent reviews project architecture)
- **pytm** (threat-model-as-code; emits threats + DFD from a Python model, OSS)
- **Semgrep** (taint/dataflow to expose trust-boundary crossings, OSS + $)
- **VVAH** (agentic attack-surface + STRIDE/OWASP threat modeling, exploit-chain findings, OSS, AI)

### `assets/security-code.md` — SAST
- **Semgrep** (rule/taint SAST, OSS + $)
- **CodeQL CLI** (semantic dataflow queries → SARIF, local, free for OSS)
- **Bandit** (Python) · **gosec** (Go) · **Brakeman** (Rails) — all OSS
- **SonarQube scanner** (quality + security hotspots; needs local server, OSS + $)
- **Snyk Code** (`snyk code test`, OSS-tier + $, cloud) `AI`
- **Fortify** (`sourceanalyzer`, local, $) · **Checkmarx CxSAST** (CLI/API, $) · **Veracode** (CLI+API, $, cloud)
- **VVAH** (multi-lens agentic SAST + adversarial verification, OSS, AI)
- **Strix** (autonomous agentic AppSec; tests code/APIs/cloud/infra → validated findings + fix PRs, freemium, cloud) `AI` — https://www.strix.ai/

### `assets/security-packages.md` — SCA (npm/PyPI/Maven/NuGet/Go…)
- **OSV-Scanner** (Google OSV DB, OSS) · **Trivy** (multi-lang, OSS) — default
- **OWASP Dependency-Check** (CVE/NVD match, OSS)
- Native: **npm audit · pip-audit · cargo-audit · dotnet list --vulnerable · govulncheck** (OSS)
- **Snyk Open Source** (SCA + fix advice, $, cloud)
- **Socket** (supply-chain / malware / typosquat behavior, $, cloud) `AI`
- **Endor Labs** (reachability to cut unreachable-CVE noise, $, cloud) `AI`

### `assets/security-iac.md` — Terraform/CFN/ARM/Bicep/Helm
- **Checkov** (multi-IaC, OSS) · **KICS** (multi-IaC, OSS)
- **tfsec** (Terraform, OSS) · **Terrascan** (policy-as-code, OSS)
- **Snyk IaC** (misconfig + fixes, $, cloud)
- **VVAH IaC lens** (OSS, AI)

### `assets/security-containers.md` — Docker images & Dockerfiles
- **Trivy** (vulns + misconfig + secrets, OSS) — default
- **Grype** (image/fs vulns, OSS) · **Dockle** (CIS/Dockerfile hygiene, OSS)
- **Syft** (SBOM, OSS) · **cdxgen** (CycloneDX SBOM, OSS)
- **Docker Scout** (image CVE + base-image advice, freemium, cloud)
- **Snyk Container** (image vulns + base upgrade advice, $, cloud)

### `assets/security-kubernetes.md`
- **kube-bench** (CIS benchmark, OSS) · **kubescape** (NSA/CIS/MITRE posture, OSS)
- **Polaris** (workload best-practice, OSS)
- **kube-hunter** (cluster attack-surface, OSS) *— active, gate*

### `assets/security-cloud.md` — CSPM (AWS/Azure/GCP)
- **Prowler** (multi-cloud checks + compliance, OSS)
- **ScoutSuite** (multi-cloud audit, OSS)
- **Steampipe** (SQL over live cloud config, OSS)

### `assets/security-secrets.md`
- **gitleaks** (history + tree, OSS) · **trufflehog** (finds + verifies live secrets, OSS)
- **detect-secrets** (baseline, OSS)
- **GitGuardian ggshield** (CLI, $, cloud)

### `assets/security-api.md` — *active, gate if hitting live endpoints*
- **Schemathesis** (OpenAPI property/fuzz, OSS) · **Nuclei** (templated checks, OSS)
- **OWASP ZAP** (headless/daemon active scan, OSS)
- **42Crunch** (OpenAPI conformance/contract, CLI, $) · **StackHawk** (CI-native DAST, CLI, $, cloud)

### `assets/security-web-dast.md` — *active, gate*
- **OWASP ZAP** (OSS) · **Nikto** (server misconfig, OSS) · **Nuclei** (OSS)

### `assets/security-gateways.md` — proxy-in-the-middle (route traffic through → it scans)
- **OWASP ZAP** (proxy daemon; passive + active scan of traffic, OSS)
- **mitmproxy** (scriptable intercept; custom scan addons, OSS)
- **Nuclei** (run through an upstream proxy against captured routes, OSS)
- **Burp Suite DAST/Enterprise** (REST-API driven scan, $) — the scriptable, non-GUI Burp
- **garak** (point at an LLM gateway/endpoint → probes it, OSS, AI)

### `assets/security-dns-recon.md` — *offensive, HARD-GATE (ownership required)*
- **amass** (subdomain enum + mapping, OSS) · **subfinder** (passive enum, OSS)
- **dnsrecon** (records/zone, OSS) · **dnstwist** (typosquat/phishing domains, OSS)

### `assets/security-network-pentest.md` — *offensive, HARD-GATE*
- **nmap** (port/service/version, OSS) · **masscan** (fast port scan, OSS)
- **OpenVAS/Greenbone** (network vuln scan, OSS)
- **Metasploit** (exploit framework, OSS + $) · **Nessus** (vuln scanner, local service, $)

### `assets/security-exfiltration.md` — *test-only, HARD-GATE*
- **Egress-Assess** (tests exfil channels, OSS) · **DET** (data-exfil toolkit, OSS)

### `assets/security-host-compliance.md`
- **Lynis** (host hardening audit, OSS) · **OpenSCAP** (SCAP compliance, OSS)
- **CIS-CAT Pro** (official CIS assessor, $)

### `assets/security-llm-ai.md` — LLM/AI app scanners
- **garak** (jailbreak/injection/leakage/toxicity probes → report, OSS, AI)
- **PyRIT** (scripted AI red-team; attacks + scores responses, OSS, AI)
- **promptfoo** (`promptfoo redteam` adversarial suites vs endpoint, OSS, AI)

---

### `assets/security-recommend-gui-bot.md` — human-operated / hosted-console / bot (recommend to user only)

**GUI / desktop (no non-interactive entry point)**
- **Burp Suite Pro** (interactive web/API pentest workbench — GUI-driven; use ZAP headless or Burp DAST/Enterprise API for automation)
- **Microsoft Threat Modeling Tool** (Windows GUI DFD/STRIDE modeling — use pytm for scriptable)
- **OWASP Threat Dragon** (GUI threat-model editor — use pytm for scriptable)
- **IDA Pro / Ghidra GUI** (interactive reverse engineering — Ghidra has headless mode, but analysis is human-driven)

**Hosted console / SaaS (scan = "connect an account in a web UI," no CLI trigger)**
- **Wiz** (agentless CNAPP; cloud posture + attack-path graph — console/connector-based)
- **Orca Security** (agentless CNAPP — console-based)
- **Prisma Cloud** (CNAPP platform — console; OSS core is Checkov, run that locally instead)
- **Aqua Platform / Sysdig Secure** (container/k8s runtime platform — hosted control plane + agents)
- **Qualys VMDR** (SaaS/appliance vuln management — console)
- **Veracode / Checkmarx / Fortify SSC dashboards** (the scanners have CLIs — in the runnable list — but the triage/policy dashboards are console-only)
- **SonarCloud UI** (the scanner CLI is runnable; the project dashboard is hosted UI)

**Bots / platform-native (fire on the platform, not from your machine)**
- **Dependabot** (GitHub bot — auto-PRs; local analog is OSV-Scanner / native audits)
- **Copilot Autofix** (GitHub/Azure server-side remediation — hosted pipeline only)
- **GitHub code scanning default setup** (runs in Actions, not locally; CodeQL **CLI** is the local equivalent, in the runnable list)
- **Renovate** (dependency-update bot — runs as an app/CI job, not an ad-hoc AI trigger)

---

## References
- Anthropic — Assessing Claude Mythos Preview's cybersecurity capabilities: https://red.anthropic.com/2026/mythos-preview/
- Anthropic — Claude Fable 5 and Claude Mythos 5: https://www.anthropic.com/news/claude-fable-5-mythos-5
- Fortune — Universal jailbreaks in GPT-5.6; U.S. government forced Anthropic to disable Fable 5: https://fortune.com/2026/07/10/openai-gpt-5-6-sol-jailbreaks-cyber-attacks-similar-to-security-flaw-that-led-u-s-government-to-force-anthropic-to-disable-fable-5/
- Google Cloud Threat Intelligence — Adversaries leverage AI for vulnerability exploitation and initial access: https://cloud.google.com/blog/topics/threat-intelligence/ai-vulnerability-exploitation-initial-access
- France24 — OpenAI reports "unprecedented" autonomous hack by AI agents: https://www.france24.com/en/live-news/20260722-openai-reports-unprecedented-autonomous-hack-by-ai-agents
- Visa Vulnerability Agentic Harness (VVAH): https://github.com/visa/visa-vulnerability-agentic-harness
- Mend — Best SAST Tools in 2026: https://www.mend.io/blog/best-sast-tools/

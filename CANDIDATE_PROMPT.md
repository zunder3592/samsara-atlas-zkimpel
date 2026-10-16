# Samsara Atlas - Take-Home Assessment

## Instructions

Thank you for your interest in the Staff AI Engineer, People role. This assessment
evaluates your ability to identify production risks, improve architecture, and
scale AI systems that touch real employee data.

### Setup

1. Fork this repo
2. `make setup` then `make seed`
3. Create `.env` with `PROVIDER_TYPE=ollama` (or use `make api-ollama`)
4. Run `make api` (terminal 1) and `make ui` (terminal 2)
5. Install [Ollama](https://ollama.ai) and `ollama pull llama3.2`

All employee records and case content are synthetic fixtures generated for this
assessment - there is no real employee data anywhere in this repo.

### What to Do

1. **Review the codebase** - Run the system, submit a case or two, and understand
   the architecture: HRIS context retrieval, policy retrieval, summarization,
   response drafting, and case-note logging.

2. **Identify risks** - Find architectural and production risks. Consider:
   - Concurrency and correctness
   - Observability and debuggability
   - Reliability and retry semantics
   - Data integrity and replay/auditability behavior
   - Abstraction boundaries and provider independence
   - Data privacy and handling of sensitive employee information

3. **Prioritize and fix** - Address the most important issues. Add tests where
   useful. You will not have time to fix everything - prioritization is part of
   what we're evaluating.

4. **Design note** - Write a brief design note (1-2 pages) describing:
   - Issues found (with severity)
   - Changes made
   - Tradeoffs considered
   - What you would still want to fix or verify before this touched real
     employee data in production
   - Next steps for scaling

### Deliverables

- Fixed/improved code (PR against your fork)
- New or updated tests
- Design note (DESIGN_NOTE.md)

### Tips

- The system works on the happy path; focus on edge cases, concurrency, and scale.
- Run `make load`; it may reveal subtle behavior.
- No external credentials required; everything runs locally.
- Use Ollama for real LLM output - it makes the demo more engaging.
- This system is a stand-in for the kind of employee-facing tooling this role
  builds day to day. Treat its outputs and its data handling with the same
  scrutiny you'd bring to something that would actually reach a Samsarans's
  inbox.

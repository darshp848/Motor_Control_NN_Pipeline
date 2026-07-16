---
name: progress-motor-control-foundry
description: Advance work in Motor_Control_NN_Pipeline from an underspecified goal to the next verified milestone. Use for EESM/IPM pipeline changes, Maxwell/AEDT diagnosis or campaigns, sampling and provenance, surrogate selection, controller/LUT artifacts, research handoff, or whenever progress is foundering because the technical state and next gate are unclear.
---

# Progress Motor Control Foundry

Turn the user's desired outcome into a bounded engineering contract, reconstruct the repository's actual state, and complete only the next evidence-backed milestone. Carry the technical prompting burden: ask the user for intent or authorization, not facts that can be discovered from the repository and primary documentation.

## 1. Reconstruct the State

1. Read the root `AGENTS.md`, `README.md`, `docs/EESM_PIPELINE_ARCHITECTURE.md`, and the current plan or qualification document for the affected stage.
2. Inspect `git status`, the relevant manifest/schema, focused tests, current output status, and preserved failure evidence.
3. Determine the requested outcome, last accepted artifact, current blocking gate, authoritative files, and smallest action that could advance or disprove the current hypothesis.
4. Treat unverified prose and generated output as claims to check, not source-of-truth replacements.

For work expected to span several turns, copy `assets/active-task-template.md` to an ignored local work location and keep it current. Do not commit the filled-in task note unless the user asks.

## 2. Translate the Goal Into a Contract

State a compact contract before making consequential changes:

- **Outcome:** what becomes possible when this milestone succeeds.
- **Current gate:** the exact reason the project cannot advance yet.
- **Scope:** files, subsystem, stage, and allowed external operations.
- **Evidence:** observable outputs that prove success or failure.
- **Stop rule:** the condition that ends the attempt without speculative retries.
- **Not included:** later stages and claims that remain blocked.

If a missing choice changes architecture, safety, cost, or campaign scope, ask. Otherwise infer the technical details from local evidence and current primary sources.

## 3. Choose the Next Milestone

Prefer, in order:

1. resolve contradictions between the stated contract and actual artifacts;
2. reproduce or isolate the current failure with a non-destructive diagnostic;
3. make the smallest implementation change covered by a contract or regression check;
4. validate the next stage without entering the stage after it.

Do not bundle model construction, mesh generation, solving, normalization, fitting, and training into one attempt. A passing earlier stage authorizes proposing the next stage; it does not silently authorize running it.

## 4. Execute Research-First

For AEDT/Maxwell, Simulink, hardware, third-party APIs, or version-sensitive libraries:

1. inspect the installed version, local configuration, logs, saved projects, and known-good examples;
2. consult current primary vendor documentation;
3. record the supported workflow, plausible causes, diagnostic, and distinguishing evidence;
4. run the smallest safe diagnostic;
5. stop after two recurrences of the same failure or an application crash, preserve the evidence, and research again.

For repository-only work with an established contract, implement directly and use focused tests. Use `apply_patch`, preserve unrelated dirty-worktree changes, and avoid broad refactors unless the milestone requires them.

## 5. Enforce Foundry Gates

- Keep the foundry authoritative and the research repository downstream.
- Keep frozen sampling identities, roles, seeds, hashes, and scheduler-audit separation immutable.
- Preserve failed campaigns and raw provenance; create a new revision instead of rewriting history.
- Leave numerical gates at `baseline_required` until independent evidence supports them.
- Require model inventory/design validation and an initial mesh before a field solve.
- Require qualification before campaign expansion, canonical evidence before fitting, independent selection before promotion, and promotion before LUT audit or controller claims.
- Do not start AEDT/Maxwell, Simulink, training, or a new campaign without explicit user authorization and satisfied prerequisites.

When working under `aedt_mcp/`, also follow its nested `AGENTS.md`.

## 6. Verify and Hand Off

Run focused validation first. Expand to the full offline suite only when the change can affect broader contracts. Do not launch an external application merely to validate documentation or workflow files.

Finish with a checkpoint containing the milestone outcome, changed files and generated evidence, exact verification results, passed and blocked gates, assumptions or unresolved risks, and one recommended next action with the authorization it would require.

Stop at the agreed milestone. Do not roll into Task 10, solver operation, training, research publication, commit, or push without an explicit request.

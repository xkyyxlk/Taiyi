# Evaluation

Run all reproducible v0.1 experiments with:

```bash
taiyi --data-dir .taiyi-eval experiment run all --output-dir experiments
```

Each run uses a fresh SQLite database, deterministic `MockProvider`, and writes `report.json`.

| Experiment | Primary checks |
|---|---|
| same-origin-fork | shared base, distinct worldlines, event isolation |
| conflict-merge | conflict detection, explicit review, suspended uncertainty |
| memory-rebirth | new snapshot, two-branch provenance, inheritance by rebirth |

`taiyi evaluate` reports source accuracy, false-memory rate, event sequence validity, branch
fidelity, identity stability, deletion completeness, and pollution resistance. Conflict
detection rate needs labeled expected conflicts, so the general evaluator returns it as
unavailable and the conflict experiment supplies the labeled check.

These are engineering measurements of stored records and workflow behavior. They are not
measurements of consciousness or subjective experience.

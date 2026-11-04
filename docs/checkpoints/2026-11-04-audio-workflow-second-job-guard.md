# Source-only second-job injection prevention — 2026-11-04

Continuing from DRAFT PR #397, the source quarantine checker previously only looked for the known microphone/dialogue job with an inert if condition. It did not reject an additional active job in the same jobs mapping. This could give misleading safety-gate evidence.

The strengthened source-only check requires exactly one top-level job with the expected name, exactly one bare YAML false guard and exactly one approved self-hosted VENTUNO runner. Unexpected second jobs, duplicate guards, changed runner and nonliteral conditions fail closed. Synthetic tests cover all six historical workflows.

No microphone, speaker, production setting, NPU or VENTUNO job is accessed by this change. This is a structural safeguard for this DRAFT commit, not a full YAML parser and not proof that previous remote branches are disabled. Do not reuse prior October audio approvals for current recording or for a full STT/GenieX dialogue.

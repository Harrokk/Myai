# Voice side-effect retry quarantine (source-only, opt-in stack)

## Risk addressed

An explicit `Stop` during a voice write, or an exception after a
state change, can produce an `unknown`, `failed` or partially
completed execution outcome. The current voice session cannot prove
which external effects already occurred. Repeating the phrase can
duplicate writes, purchases, file updates or commands.

## New behavior

`MyAICore` owns a **process-local**, sticky
`VoiceRetryQuarantine`. Once a guarded voice batch produced an
uncertain result **and at least one effectful tool was actually
attempted**, the same core refuses all **new effectful voice tool
invocations**, even with fresh spoken approval or a Stop/Start
cycle. Quarantine also latches if Stop arrived just after a
previously completed effectful call while the LLM was processing
its response. The block is checked at whole-plan preflight and at
the live invocation boundary.

Known allowlisted read-only status tools continue to work.
A completely unexecuted denied batch or a failed known-safe read
does **not** trigger quarantine. Typed-text tool dispatch preserves
the existing contract. No raw transcript, selected arguments,
token or user data is placed in the quarantine; it stores only
a boolean. The voice interface returns a fixed manual-review
message and a sanitized `manual_reconciliation_required` flag
when a new effectful command is blocked. It does **not**
automatically replay or create a fresh action.

An error raised after the Stop signal now reports `unknown`
rather than implying `failed`; it cannot prove that earlier
side effects did not occur.

## Recovery and known limitations

This DRAFT is **not** an exactly-once execution ledger:
the quarantine is in memory only and disappears when
`MyAICore` is recreated or the process restarts. Do **not**
claim that it survives reboot, coordinates concurrent separate
MyAI processes, or prevents equivalent actions performed with a
different text command/interface. No voice shortcut clears
the quarantine. A human should verify the actual external state
before deliberately restarting the assistant or attempting
further writes.

A durable, pre-invocation journal with atomic transaction receipts
and a trusted manual reconciliation path must be designed and
tested separately before sensitive write actions are enabled.
Never solve this by storing raw voice transcripts in audit files
or automatically retrying uncertain writes.

## Audit boundaries

Tests are synthetic functions only with disposable workspaces.
No active VENTUNO service, HTP/NPU, microphone, native
FasterWhisper, firmware, systemd or local memory database is
modified. This is source-only defense-in-depth and remains
stacked in an unmerged DRAFT PR.

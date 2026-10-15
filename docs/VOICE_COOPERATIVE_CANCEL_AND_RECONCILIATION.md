# Cooperative cancellation for guarded voice tools — source-only DRAFT

## Contract (opt-in, no background service)

Existing `run_tools` calls and typed-text behavior are unchanged. A voice tool may explicitly declare the boolean `safety.voice_cancel_callback=true` on its registry entry. Only a guarded voice request with a valid, callable per-utterance Stop probe is then eligible to invoke the callback, and the tool function must expose an **explicit keyword-only** `cancel_requested` parameter:

```python
def long_operation(user_input, *, cancel_requested):
    for batch in bounded_batches:
        if cancel_requested() is not False:
            # Stop before performing the NEXT action; do not claim rollback
            return ToolOutcome(False)
        apply_one_batch(batch)
    return ToolOutcome(True, "finished")
```

With `pass_user_input=true`, the function receives its original single user input plus the keyword-only probe. Without user input, it receives only `cancel_requested`. The probe must be called by the tool **between** individually safe operations; MyAI does not inject OS signals or threads into running arbitrary functions.

`run_tools` checks opt-in signature and probe availability during **whole-batch preflight** and again at invocation; malformed declarations block the entire batch before any action. A mutation of the opt-in flag after spoken high-risk authorization changes the signed safety metadata and invalidates HMAC verification. Legacy callbacks are invoked without any new argument. `safety.voice_cancel_callback` must be a literal boolean; strings and other values are rejected.

Regardless of callback cooperation, a Stop observed **after** an invocation began is reported conservatively as `unknown, attempted=true` (the callback may have written something before Stop); all subsequent steps are blocked. Do not infer that `ToolOutcome(False)` proves rollback. Failure of the Stop probe fails closed without exporting exceptions or raw tool output.

## Recovery after an uncertain outcome

When guarded voice outcomes are `unknown` or `partially_completed`, MyAICore exposes `manual_reconciliation_required=true`. The voice pipeline forwards **only that boolean** alongside its already-sanctioned `tool_execution.status`; it never forwards raw arguments, secret error text or a pending tool command. Before any retry, the operator should inspect the target state and decide what is still required. Repeating a potentially partial write automatically risks duplication. There is no automatic retry or implicit replay introduced here.

A token/event cannot atomically cancel a Python callback already running, native I/O that ignores the probe, or a SQLite transaction already started. This opt-in contract adds a cooperative path only; live-device and durable recovery tests are separate tasks requiring physical access and explicit authorization.

## Focused security review

* Invocation flow: preflight validation, at-call validation, post-call unknown accounting, and no automatic retry
* Metadata: consent HMAC includes `safety`, including the new opt-in flag
* Privacy: synthetic regression fixtures contain no real transcripts; UI forwards a boolean/status only
* Isolation: no real microphone, native STT, model, HTP/NPU, terminal, systemd, firmware or service change

The prior six static-audit review flags remain documented in `docs/VOICE_INFLIGHT_STOP_AND_SIX_CALL_REVIEW.md`; one production STT launcher still requires native process containment checks. Do not mark this code production-deployed on the basis of source-only CI.

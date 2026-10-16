import sqlite3
from contextlib import nullcontext
import threading
from pathlib import Path

from core.audit_log import (
    AuditLogger,
    audit_outcome_for_exception,
)
from core.error_log import ErrorLogger
from core.intermediate_results import (
    IntermediateResultStore,
)
from core.memory import MemoryStore
from core.memory_lifecycle import apply_memory_lifecycle
from core.memory_policy import assess_memory_candidate
from core.memory_feedback import (
    explicit_memory_request,
    memory_write_feedback,
)
from core.llm_factory import build_llm_client
from core.health_status import (
    build_health_status,
    read_health_state,
    write_health_state,
)
from core.orchestration import public_plan
from core.voice_plan_attestation import allow_voice_dispatch
from core.voice_retry_quarantine import VoiceRetryQuarantine, known_voice_read_only
from core.voice_write_journal import VoiceWriteAheadMarker
from core.tool_outcome import summarize_guarded_outcomes
from core.tool_manager import (
    EXECUTION_BLOCKED_MESSAGE,
    EXECUTION_FAILED_MESSAGE,
    EXECUTION_INTERRUPTED_MESSAGE,
    load_tools,
    run_tools,
    select_tool_plan,
)


class MyAICore:
    def __init__(self, settings, project_root, tools=None, memory=None, llm=None):
        self.settings = settings
        self._response_lock = threading.RLock()
        # Prevent unverified replays of effectful voice commands across
        # Stop -> Start within this MyAICore process. Not crash-durable.
        self._voice_retry_quarantine = VoiceRetryQuarantine()
        self._voice_write_journal = VoiceWriteAheadMarker(project_root)
        self.project_root = project_root
        self.error_logger = ErrorLogger(
            settings,
            project_root,
        )
        self.audit_logger = AuditLogger(
            settings,
            project_root,
        )

        self.llm_provider = (
            settings.get("llm", {})
            .get("provider", "ollama")
            .strip()
            .lower()
        )
        self.ollama_url = settings["ollama"]["url"]

        provider_config = (
            settings.get("geniex", {})
            if self.llm_provider == "geniex"
            else settings["ollama"]
        )
        configured_model = provider_config.get(
            "model",
            settings["ollama"]["model"],
        )

        database_path = project_root / settings["memory"]["database"]

        self.memory = memory or MemoryStore(
            database_path,
            max_search_results=settings["memory"]["max_search_results"],
        )

        self.llm = llm or build_llm_client(
            settings,
            project_root=project_root,
        )
        self.llm_provider = getattr(
            self.llm,
            "provider_name",
            self.llm_provider,
        )
        self.model = getattr(
            self.llm,
            "model",
            configured_model,
        )
        self.llm_url = getattr(
            self.llm,
            "url",
            self.ollama_url,
        )

        self.tools = (
            tools
            if tools is not None
            else load_tools(
                error_logger=self.error_logger,
            )
        )
        self.max_conversation_turns = settings.get(
            "conversation",
            {},
        ).get("max_turns", 6)
        self.conversation_history = []
        self._memory_lookup_status = "not_checked"
        intermediate = settings.get(
            "intermediate_results",
            {},
        )
        self.intermediate_results = IntermediateResultStore(
            max_pending=intermediate.get(
                "max_pending",
                5,
            ),
            max_query_chars=intermediate.get(
                "max_query_chars",
                240,
            ),
            max_age_seconds=intermediate.get(
                "max_age_seconds",
                1800,
            ),
        )
        self.system_profile = self._build_system_profile()

    def _build_system_profile(self):
        assistant = self.settings["assistant"]
        provider_label = {
            "ollama": "Ollama",
            "geniex": "Qualcomm GenieX",
        }.get(
            self.llm_provider,
            self.llm_provider,
        )
        current_platform = assistant.get(
            "current_platform",
            "Windows-dator",
        )
        compute_accelerator = str(
            assistant.get(
                "compute_accelerator",
                "",
            )
            or "okänd"
        ).strip()
        future_target = str(
            assistant.get(
                "future_target",
                "",
            )
            or ""
        ).strip()
        target_line = (
            (
                "Planerad målhårdvara är "
                f"{future_target}."
            )
            if future_target
            else (
                "Nuvarande plattform är den aktiva "
                "embedded-målplattformen."
            )
        )

        return f"""
Du är MyAI, en lokal personlig AI-assistent.

Din språkmodell är {self.model}.
Du körs genom {provider_label}.
Du kör för närvarande på {current_platform}.
Beräkningsaccelerator: {compute_accelerator}.

Du har ett separat långtidsminne som hanteras av Python och SQLite.

Utvecklingsmiljön kan använda en annan LLM-provider än målhårdvaran.
{target_line}

Svara på svenska när användaren skriver svenska.
Var saklig och tydlig.
Hitta inte på information om användaren.
Använd information från minnessystemet när den är relevant.
"""

    def initialize(self):
        self.memory.init()

    def build_system_message(
        self,
        user_message,
        tool_results=None,
        pending_intermediate_results=None,
    ):
        try:
            relevant_memories = self.memory.search(user_message)
            memory_text = self.memory.format(relevant_memories)
        except (sqlite3.Error, OSError):
            # Do not tell the LLM "no relevant memories" when SQLite
            # cannot be read. Do not export exception text / DB path.
            # This turn must also avoid new automatic memory writes.
            self._memory_lookup_status = "unavailable"
            memory_text = (
                "Långtidsminnet är tillfälligt otillgängligt. "
                "Dra inga slutsatser om vad som tidigare sparats. "
                "Svara med tillgänglig information och ange osäkerhet."
            )
        else:
            self._memory_lookup_status = "available"

        system_message = (
            self.system_profile
            + """

Relevant information från långtidsminnet:

"""
            + memory_text
        )

        health = self._health_status()
        health_reasons = "; ".join(
            health.get(
                "reasons",
                [],
            )
        )
        system_message += (
            """

Intern read-only systemhälsa:

"""
            f"Nivå: {health.get('level', 'unknown')}\n"
            f"Aktiv LLM-backend: "
            f"{health.get('llm_runtime', {}).get('active_backend', 'primary')}\n"
            f"GenieX-fel i rad: "
            f"{health.get('geniex_consecutive_failures', 0)}\n"
            f"GenieX lyckade kontroller i rad: "
            f"{health.get('geniex_consecutive_successes', 0)}\n"
            f"LLM-routing: "
            f"{health.get('llm_runtime', {}).get('routing_reason', '')}\n"
            f"Detaljer: {health_reasons}\n"
            "Använd statusen endast när den är relevant. "
            "Påstå inte att ett hårdvarufel är verifierat om statusen är unknown eller stale."
        )

        if pending_intermediate_results:
            commands = ", ".join(
                item.get(
                    "confirmation_command",
                    "",
                )
                for item in pending_intermediate_results
                if item.get(
                    "confirmation_command"
                )
            )
            system_message += (
                """

Ett eller flera read-only nästa steg har förberetts men HAR INTE körts.
Webbresearch får inte påstås vara utförd innan användaren skickar exakt
bekräftelsekommandot som anges nedan.

Tillgängliga bekräftelser:
"""
                + commands
                + """
"""
            )

        if tool_results is not None:
            system_message += (
                """

Lokala systemverktyg har körts på användarens begäran.

Resultaten från verktygen är:

"""
                + str(tool_results)
                + """

Använd resultatet ovan när du svarar på användarens fråga.
Hitta inte på värden som inte finns i resultatet.
Svara kort och tydligt på svenska.
"""
            )

        return system_message

    def _prior_user_messages(self):
        return [
            item["content"]
            for item in self.conversation_history
            if item.get("role") == "user"
        ]

    def _record_memory_audit_result(self, decision, **event):
        """Record a completed/failed memory attempt without losing its outcome.

        The memory write or queue operation has already been attempted.
        An audit-log failure here must NOT trigger a retry, hide a
        successful write, or raise a second exception over the first.
        Whether the event was physically persisted is then unverified.
        """
        try:
            self.audit_logger.write_result(**event)
        except Exception:
            decision["audit_result_status"] = "unverified"
            decision["audit_result_error"] = (
                "Minnesåtgärdens slutliga revisionslogg kunde inte "
                "verifieras."
            )
        else:
            # One decision may emit both auto-save and review audit
            # events. A later successful event cannot erase the fact
            # that an earlier completion event was unverified.
            if decision.get("audit_result_status") != "unverified":
                decision["audit_result_status"] = "recorded"

    def _queue_memory_review(
        self,
        decision,
    ):
        enqueue = getattr(
            self.memory,
            "enqueue_review",
            None,
        )

        if not callable(
            enqueue
        ):
            decision[
                "review_queued"
            ] = False
            return decision

        config = self.settings.get(
            "memory",
            {},
        )

        if not config.get(
            "review_queue_enabled",
            True,
        ):
            decision[
                "review_queued"
            ] = False
            return decision

        conflicts = [
            item.get(
                "id"
            )
            for item in (
                decision.get(
                    "conflicts",
                    [],
                )
                or []
            )
            if isinstance(
                item,
                dict,
            )
            and item.get(
                "id"
            ) is not None
        ]
        reason_parts = [
            str(
                item
            ).strip()
            for item in (
                decision.get(
                    "reasons",
                    [],
                )
                or []
            )
            if str(
                item
            ).strip()
        ]

        lifecycle_action = str(
            decision.get(
                "lifecycle_action",
                ""
            )
            or ""
        ).strip()

        if lifecycle_action:
            reason_parts.append(
                (
                    "lifecycle_action="
                    + lifecycle_action
                )
            )

        try:
            self.audit_logger.write_attempt(
                action="memory_review_enqueue",
                component="memory",
                target=(
                    "memory_review/pending"
                ),
                details={
                    "category": decision.get(
                        "category",
                        "other",
                    ),
                    "conflict_count": len(
                        conflicts
                    ),
                },
            )
        except Exception as error:
            decision[
                "review_queued"
            ] = False
            decision[
                "review_queue_error"
            ] = "Minnesgranskningen kunde inte köas."
            return decision

        try:
            result = enqueue(
                decision.get(
                    "category",
                    "other",
                ),
                decision.get(
                    "content",
                    "",
                ),
                reason="; ".join(
                    reason_parts
                ),
                conflict_ids=conflicts,
            )
        except Exception as error:
            self._record_memory_audit_result(
                decision,
                action="memory_review_enqueue",
                component="memory",
                outcome=(
                    audit_outcome_for_exception(
                        error
                    )
                ),
                target="memory_review/pending",
                details={
                    "error_type": type(
                        error
                    ).__name__,
                },
            )
            decision[
                "review_queued"
            ] = False
            decision[
                "review_queue_error"
            ] = "Minnesgranskningen kunde inte köas."
            return decision

        decision[
            "review_queued"
        ] = True
        decision[
            "review_id"
        ] = result.get(
            "review_id"
        )
        decision[
            "review_created"
        ] = bool(
            result.get(
                "created"
            )
        )
        self._record_memory_audit_result(
            decision,
            action="memory_review_enqueue",
            component="memory",
            outcome="success",
            target=(
                "memory_review/"
                + str(
                    result.get(
                        "review_id"
                    )
                )
            ),
            details={
                "created": bool(
                    result.get(
                        "created"
                    )
                ),
                "conflict_count": len(
                    conflicts
                ),
            },
        )
        return decision


    @staticmethod
    def _voice_stop_probe(voice_plan_verifier):
        """Only a real per-utterance Stop hook qualifies for cooperative IO.

        A naked voice-plan approval lambda is not an active Stop source:
        tools that explicitly require cooperative cancellation must fail
        closed rather than receiving a callback that always says False.
        """
        if voice_plan_verifier is None:
            return None
        try:
            candidate = getattr(
                voice_plan_verifier, "voice_stop_requested", None
            )
            return candidate if callable(candidate) else None
        except BaseException:
            return None

    @staticmethod
    def _voice_stop_requested(voice_plan_verifier):
        """Fail closed on malformed or failing per-utterance Stop tokens.

        Typed-text responders and historical verifier callbacks without
        cancellation metadata keep their existing behavior.
        """
        if voice_plan_verifier is None:
            return False
        try:
            check = getattr(voice_plan_verifier, "voice_stop_requested", None)
            if check is None:
                return False
            return not callable(check) or check() is not False
        except BaseException:
            return True

    @staticmethod
    def _voice_cancelled_memory_decision():
        return {
            "action": "deferred_voice_cancelled",
            "saved": False,
            "reasons": ["Röstsessionen avbröts före minneslagring."],
        }

    def _consider_long_term_memory(self, user_message, *, voice_plan_verifier=None):
        if self._voice_stop_requested(voice_plan_verifier):
            return self._voice_cancelled_memory_decision()
        config = self.settings.get("memory", {})

        if not config.get("auto_assess_enabled", True):
            return {
                "action": "disabled",
                "saved": False,
                "score": 0,
                "category": "other",
                "content": "",
                "sensitive": False,
                "reasons": [
                    "Automatisk minnesbedömning är avstängd."
                ],
            }

        decision = assess_memory_candidate(
            user_message,
            settings=self.settings,
            prior_messages=self._prior_user_messages(),
        )
        decision = dict(decision)
        decision["saved"] = False

        if self._voice_stop_requested(voice_plan_verifier):
            return self._voice_cancelled_memory_decision()

        if (
            decision.get("action") == "save"
            and config.get("auto_save_enabled", True)
            and not decision.get("sensitive")
            and decision.get("content")
        ):
            try:
                self.audit_logger.write_attempt(
                    action="memory_auto_store",
                    component="memory",
                    target=(
                        "memory/"
                        + str(
                            decision.get(
                                "category",
                                "other",
                            )
                        )
                    ),
                    details={
                        "category": decision.get(
                            "category",
                            "other",
                        ),
                    },
                )
            except Exception as error:
                decision[
                    "saved"
                ] = False
                decision[
                    "lifecycle_action"
                ] = "audit_blocked"
                decision[
                    "audit_error"
                ] = "Minnesåtgärdens revisionslogg misslyckades."
                return decision

            # An audit attempt does not authorize a write after Stop.
            if self._voice_stop_requested(voice_plan_verifier):
                return self._voice_cancelled_memory_decision()

            try:
                lifecycle = apply_memory_lifecycle(
                    self.memory,
                    decision,
                    original_text=user_message,
                    settings=self.settings,
                )
            except Exception as error:
                self._record_memory_audit_result(
                    decision,
                    action="memory_auto_store",
                    component="memory",
                    outcome=(
                        audit_outcome_for_exception(
                            error
                        )
                    ),
                    target=(
                        "memory/"
                        + str(
                            decision.get(
                                "category",
                                "other",
                            )
                        )
                    ),
                    details={
                        "error_type": type(
                            error
                        ).__name__,
                    },
                )
                decision[
                    "saved"
                ] = False
                decision[
                    "lifecycle_action"
                ] = "failed"
                decision[
                    "memory_error"
                ] = "Långtidsminnet kunde inte uppdateras."
                return decision

            decision.update(
                lifecycle
            )
            self._record_memory_audit_result(
                decision,
                action="memory_auto_store",
                component="memory",
                outcome="success",
                target=(
                    "memory/"
                    + str(
                        decision.get(
                            "category",
                            "other",
                        )
                    )
                ),
                details={
                    "saved": bool(
                        lifecycle.get(
                            "saved"
                        )
                    ),
                    "lifecycle_action": (
                        lifecycle.get(
                            "lifecycle_action",
                            ""
                        )
                    ),
                },
            )

            if lifecycle.get(
                "requires_review",
                False,
            ):
                decision[
                    "action"
                ] = "review"

        if self._voice_stop_requested(voice_plan_verifier):
            # A store already completed cannot be rolled back. Preserve
            # its actual saved/review state instead of falsely denying it.
            return (decision if decision.get("saved")
                    else self._voice_cancelled_memory_decision())

        if (
            decision.get(
                "action"
            )
            == "review"
            and not decision.get(
                "sensitive",
                False,
            )
            and decision.get(
                "content"
            )
        ):
            self._queue_memory_review(
                decision
            )

        return decision

    def _intermediate_enabled(
        self,
    ):
        return bool(
            self.settings.get(
                "intermediate_results",
                {},
            ).get(
                "enabled",
                True,
            )
        )

    def _create_pending_intermediate_results(
        self,
        tool_plan,
        tool_results,
    ):
        if not self._intermediate_enabled():
            return []

        results = (
            tool_results
            if isinstance(
                tool_results,
                dict,
            )
            else {}
        )
        pending = []

        for step in (
            tool_plan.get(
                "deferred_steps",
                [],
            )
            or []
        ):
            source_tool = step.get(
                "source_tool"
            )
            target_tool = step.get(
                "next_tool"
            )

            if (
                source_tool not in results
                or target_tool not in self.tools
            ):
                continue

            item = self.intermediate_results.create(
                source_tool=source_tool,
                source_result=results.get(
                    source_tool
                ),
                target_tool=target_tool,
            )

            if item is None:
                continue

            public = self.intermediate_results.public_item(
                item
            )

            if public is not None:
                pending.append(
                    public
                )

        return pending

    def _confirmed_intermediate_response(
        self,
        user_message,
        *,
        voice_mode=False,
    ):
        if not self._intermediate_enabled():
            return None

        identifier = self.intermediate_results.parse_confirmation(
            user_message
        )

        if identifier is None:
            return None

        if voice_mode:
            # An old typed intermediate confirmation has no matching
            # independent spoken-consent attestation. Never route it to
            # the legacy unguarded run_tools path from VoicePipeline.
            return (
                {
                    "source": "intermediate_voice_blocked",
                    "steps": [],
                    "deferred_steps": [],
                    "blocked_tools": [],
                },
                [],
                {
                    "intermediate_protocol": (
                        "Mellanresultatets bekräftelse kan inte "
                        "utföras med röst utan separat verifiering."
                    ),
                },
                [],
            )

        item = self.intermediate_results.get(
            identifier
        )

        if item is None:
            plan = {
                "enabled": True,
                "orchestrated": False,
                "source": (
                    "intermediate_confirmation_invalid"
                ),
                "steps": [],
                "deferred_steps": [],
                "blocked_tools": [],
                "truncated": False,
            }
            return (
                plan,
                [],
                {
                    "intermediate_protocol": (
                        "Bekräftelsen kunde inte användas: "
                        f"{identifier} är okänd eller har gått ut."
                    )
                },
                [],
            )

        target_tool = item.get(
            "target_tool"
        )

        if target_tool not in self.tools:
            plan = {
                "enabled": True,
                "orchestrated": False,
                "source": (
                    "intermediate_confirmation_unavailable"
                ),
                "steps": [],
                "deferred_steps": [],
                "blocked_tools": [],
                "truncated": False,
            }
            return (
                plan,
                [],
                {
                    "intermediate_protocol": (
                        "Bekräftelsen kunde inte köras: "
                        f"{target_tool} är inte tillgängligt."
                    )
                },
                [
                    self.intermediate_results.public_item(
                        item
                    )
                ],
            )

        orchestration = self.settings.get(
            "orchestration",
            {},
        )
        tool_results = run_tools(
            [
                target_tool
            ],
            self.tools,
            user_input=item.get(
                "query",
                "",
            ),
            error_logger=self.error_logger,
            tool_inputs={
                target_tool: item.get(
                    "query",
                    "",
                ),
            },
            result_char_limit=orchestration.get(
                "max_result_chars_per_tool",
                6000,
            ),
        )
        self.intermediate_results.consume(
            identifier
        )
        plan = {
            "enabled": True,
            "orchestrated": False,
            "source": "confirmed_intermediate",
            "steps": [
                {
                    "tool": target_tool,
                    "input": item.get(
                        "query",
                        "",
                    ),
                    "effect": "read_only",
                }
            ],
            "deferred_steps": [],
            "blocked_tools": [],
            "truncated": False,
        }
        return (
            plan,
            [
                target_tool
            ],
            tool_results,
            [],
        )

    def preview_tool_plan(self, user_message):
        """Returnera vald verktygsplan utan att köra verktygen."""
        with self._response_lock:
            return select_tool_plan(
                user_message,
                self.tools,
                self.llm,
                settings=self.settings,
            )

    def _prepare_response(self, user_message, *, voice_plan_verifier=None):
        voice_mode = voice_plan_verifier is not None
        confirmed = self._confirmed_intermediate_response(
            user_message,
            voice_mode=voice_mode,
        )

        tool_outcomes = {} if voice_mode else None

        if confirmed is not None:
            (
                tool_plan,
                tool_names,
                tool_results,
                pending_intermediate_results,
            ) = confirmed
        else:
            tool_plan = select_tool_plan(
                user_message,
                self.tools,
                self.llm,
                settings=self.settings,
            )
            tool_names = [
                step[
                    "tool"
                ]
                for step in tool_plan.get(
                    "steps",
                    []
                )
            ]
            tool_inputs = {
                step[
                    "tool"
                ]: step.get(
                    "input",
                    user_message,
                )
                for step in tool_plan.get(
                    "steps",
                    []
                )
            }

            tool_results = None

            if tool_names:
                orchestration = self.settings.get(
                    "orchestration",
                    {},
                )
                execution_guard = None
                if voice_mode:
                    # This boundary is rechecked for each invocation,
                    # against actual selected inputs and live tool metadata.
                    def execution_guard(name, entry, actual_input):
                        return (
                            self._voice_retry_quarantine.permits(name, entry)
                            and (known_voice_read_only(name, entry)
                                 or not self._voice_write_journal.review_required)
                            and allow_voice_dispatch(
                                    tool_plan,
                                    self.tools,
                                    name,
                                    entry,
                                    actual_input,
                                    voice_plan_verifier,
                                ))

                tool_results = run_tools(
                    tool_names,
                    self.tools,
                    user_input=user_message,
                    error_logger=self.error_logger,
                    tool_inputs=tool_inputs,
                    result_char_limit=orchestration.get(
                        "max_result_chars_per_tool",
                        6000,
                    ),
                    execution_guard=execution_guard,
                    outcome_details=tool_outcomes,
                    execution_cancelled=(
                        self._voice_stop_probe(voice_plan_verifier)
                        if voice_mode else None
                    ),
                    execution_before_call=(
                        (lambda name, entry, _value:
                            True if known_voice_read_only(name, entry)
                            else self._voice_write_journal.begin_effect())
                        if voice_mode else None
                    ),
                    execution_call_scope=(
                        (lambda name, entry, _value:
                            nullcontext() if known_voice_read_only(name, entry)
                            else self._voice_write_journal.active_writer())
                        if voice_mode else None
                    ),
                )
                if voice_mode:
                    self._voice_retry_quarantine.observe(
                        tool_names, self.tools, tool_outcomes,
                        stopped=self._voice_stop_requested(voice_plan_verifier),
                    )

            pending_intermediate_results = (
                self._create_pending_intermediate_results(
                    tool_plan,
                    tool_results,
                )
            )

        system_message = self.build_system_message(
            user_message,
            tool_results=tool_results,
            pending_intermediate_results=(
                pending_intermediate_results
            ),
        )

        messages = [
            {
                "role": "system",
                "content": system_message,
            }
        ]
        messages.extend(self.conversation_history)
        messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        return (
            tool_plan,
            tool_names,
            tool_results,
            pending_intermediate_results,
            messages,
            tool_outcomes,
        )

    def _llm_runtime_metadata(self):
        status = getattr(
            self.llm,
            "status",
            None,
        )

        if callable(status):
            runtime = dict(
                status()
            )
        else:
            runtime = {
                "enabled": False,
                "active_backend": "primary",
                "primary_provider": self.llm_provider,
                "primary_model": self.model,
                "fallback_provider": None,
                "fallback_model": None,
                "last_error": None,
            }

        runtime["provider"] = self.llm_provider
        runtime["model"] = self.model
        return runtime

    def _health_status(
        self,
        llm_runtime=None,
    ):
        supervisor = self.settings.get(
            "geniex_supervisor",
            {},
        )
        raw_path = supervisor.get(
            "state_path",
            "runtime/geniex_health.json",
        )
        state_path = Path(
            raw_path
        )

        if not state_path.is_absolute():
            state_path = (
                self.project_root
                / state_path
            )

        state = read_health_state(
            state_path
        )

        return build_health_status(
            (
                llm_runtime
                if llm_runtime is not None
                else self._llm_runtime_metadata()
            ),
            state,
            supervisor_expected=bool(
                supervisor.get(
                    "enabled",
                    False,
                )
            ),
            stale_after_seconds=supervisor.get(
                "state_stale_seconds",
                30.0,
            ),
        )

    def _persist_health_status(
        self,
        health,
    ):
        raw_path = (
            self.settings
            .get(
                "health",
                {},
            )
            .get(
                "state_path",
                "runtime/myai_health.json",
            )
        )
        path = Path(
            raw_path
        )

        if not path.is_absolute():
            path = (
                self.project_root
                / path
            )

        try:
            write_health_state(
                path,
                health,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _tool_dispatch_was_blocked(tool_results):
        return isinstance(tool_results, dict) and any(
            value in (
                EXECUTION_BLOCKED_MESSAGE,
                EXECUTION_FAILED_MESSAGE,
                EXECUTION_INTERRUPTED_MESSAGE,
            )
            for value in tool_results.values()
            if isinstance(value, str)
        )

    def _finalize_response(
        self,
        user_message,
        answer,
        tool_names,
        tool_results,
        tool_plan=None,
        pending_intermediate_results=None,
        streamed=False,
        tool_outcomes=None,
        on_finalized_chunk=None,
        voice_plan_verifier=None,
    ):
        cancelled = self._voice_stop_requested(voice_plan_verifier)
        if voice_plan_verifier is not None:
            # Stop can race AFTER guarded dispatch and BEFORE the LLM
            # returns. A previously successful effect must not become
            # freely repeatable merely because Stop arrived later.
            self._voice_retry_quarantine.observe(
                tool_names, self.tools, tool_outcomes, stopped=cancelled,
            )
        if cancelled:
            memory_decision = self._voice_cancelled_memory_decision()
        elif self._memory_lookup_status == "unavailable":
            # Memory reads failed: don't attempt automatic writes or
            # claim that a new user preference has been persisted.
            memory_decision = {
                "action": "deferred_memory_unavailable",
                "saved": False,
                "reasons": [
                    "Långtidsminnet kunde inte läsas; inget nytt minne sparades."
                ],
            }
        else:
            memory_decision = self._consider_long_term_memory(
                user_message, voice_plan_verifier=voice_plan_verifier,
            )

        cancelled = self._voice_stop_requested(voice_plan_verifier)
        feedback = memory_write_feedback(
            user_message, memory_decision, self._memory_lookup_status
        )
        if feedback["message"] and not self._tool_dispatch_was_blocked(tool_results):
            if tool_names:
                # A mixed memory+tool command must keep the other
                # answer, but finish with an authoritative memory notice.
                answer = (str(answer or "") + "\n\n" + feedback["message"])
            else:
                # A pure spoken "kom ihåg" request must not be left
                # with a hallucinated claim that it was saved.
                answer = feedback["message"]

        if not cancelled and on_finalized_chunk is not None:
            on_finalized_chunk(answer)

        # A cancelled voice request must not be appended as an ordinary
        # completed dialogue. Typed text remains unchanged.
        if not cancelled:
            self._remember_conversation_turn(
                user_message,
                answer,
            )

        llm_runtime = self._llm_runtime_metadata()
        health = self._health_status(
            llm_runtime
        )
        # The background health snapshot is also a local file write.
        # Do not persist it for a cancelled voice turn.
        if not cancelled:
            self._persist_health_status(
                health
            )

        return {
            "answer": answer,
            "tools": tool_names,
            "tool_results": tool_results or {},
            "tool_dispatch_blocked": (
                cancelled or self._tool_dispatch_was_blocked(tool_results)
            ),
            "tool_outcomes": tool_outcomes or {},
            "tool_execution_status": (
                summarize_guarded_outcomes(tool_outcomes)
                if tool_outcomes is not None else "not_applicable"
            ),
            # Fixed UI hint: an uncertain or partly executed voice batch
            # needs human verification before any new attempt. Never
            # persist or automatically replay the original arguments.
            "manual_reconciliation_required": (
                (summarize_guarded_outcomes(tool_outcomes) in {
                    "unknown", "partially_completed",
                } if tool_outcomes is not None else False)
                or (voice_plan_verifier is not None
                    and (self._voice_retry_quarantine.review_required
                         or self._voice_write_journal.review_required))
            ),
            "orchestration_plan": public_plan(
                tool_plan
                or {
                    "source": "none",
                    "steps": [],
                }
            ),
            "pending_intermediate_results": list(
                pending_intermediate_results
                or []
            ),
            "memory_decision": memory_decision,
            "memory_lookup_status": self._memory_lookup_status,
            "memory_feedback": feedback,
            "streamed": bool(streamed),
            "llm_runtime": llm_runtime,
            "health": health,
        }

    def respond_voice(self, user_message, *, plan_verifier):
        if not callable(plan_verifier):
            raise ValueError("voice-plan-verifier-required")
        return self.respond(
            user_message, _voice_plan_verifier=plan_verifier
        )

    def respond_voice_stream(
        self, user_message, *, on_chunk=None, plan_verifier
    ):
        if not callable(plan_verifier):
            raise ValueError("voice-plan-verifier-required")
        return self.respond_stream(
            user_message,
            on_chunk=on_chunk,
            _voice_plan_verifier=plan_verifier,
        )

    def respond(self, user_message, *, _voice_plan_verifier=None):
        with self._response_lock:
            (
                tool_plan,
                tool_names,
                tool_results,
                pending_intermediate_results,
                messages,
                tool_outcomes,
            ) = self._prepare_response(
                user_message, voice_plan_verifier=_voice_plan_verifier
            )

            # Never let an LLM invent a success report for a denied
            # voice side effect. Return a deterministic blocked answer
            # without invoking the model.
            if (
                _voice_plan_verifier is not None
                and (self._voice_stop_requested(_voice_plan_verifier)
                     or self._tool_dispatch_was_blocked(tool_results))
            ):
                if self._voice_stop_requested(_voice_plan_verifier):
                    answer = (
                        "Röstsessionen avbröts. Tidigare verktygsåtgärder "
                        "kan ha genomförts; kontrollera innan du försöker igen."
                    )
                elif (self._voice_retry_quarantine.review_required
                      or self._voice_write_journal.review_required):
                    answer = (
                        "Tidigare röststyrda ändringar har osäkert utfall. "
                        "Tidigare ändringar kan finnas kvar. "
                        "Nya skrivkommandon är spärrade tills resultatet "
                        "har kontrollerats manuellt. Försök inte igen automatiskt."
                    )
                elif summarize_guarded_outcomes(tool_outcomes) == "partially_completed":
                    answer = (
                        "Flerkommandot stoppades efter att minst ett steg "
                        "hade genomförts. Tidigare ändringar kan finnas kvar. "
                        "Kontrollera resultatet innan du försöker igen."
                    )
                else:
                    answer = (
                        "Verktygsåtgärden stoppades av säkerhetskontrollen. "
                        "Säg hela kommandot igen om det fortfarande ska köras."
                    )
            else:
                answer = self.llm.chat(
                    messages,
                    timeout=300,
                )

            return self._finalize_response(
                user_message,
                answer,
                tool_names,
                tool_results,
                tool_plan=tool_plan,
                pending_intermediate_results=(
                    pending_intermediate_results
                ),
                streamed=False,
                tool_outcomes=tool_outcomes,
                voice_plan_verifier=_voice_plan_verifier,
            )

    def respond_stream(
        self,
        user_message,
        on_chunk=None,
        *,
        _voice_plan_verifier=None,
    ):
        with self._response_lock:
            # Buffer explicit memory requests until the persistence
            # decision is known. Never stream an early speculative
            # "saved" claim into voice or a chat UI.
            delayed_memory_feedback = explicit_memory_request(user_message)
            callback = on_chunk if delayed_memory_feedback else None
            (
                tool_plan,
                tool_names,
                tool_results,
                pending_intermediate_results,
                messages,
                tool_outcomes,
            ) = self._prepare_response(
                user_message, voice_plan_verifier=_voice_plan_verifier
            )

            if (
                _voice_plan_verifier is not None
                and (self._voice_stop_requested(_voice_plan_verifier)
                     or self._tool_dispatch_was_blocked(tool_results))
            ):
                if self._voice_stop_requested(_voice_plan_verifier):
                    answer = (
                        "Röstsessionen avbröts. Tidigare verktygsåtgärder "
                        "kan ha genomförts; kontrollera innan du försöker igen."
                    )
                elif (self._voice_retry_quarantine.review_required
                      or self._voice_write_journal.review_required):
                    answer = (
                        "Tidigare röststyrda ändringar har osäkert utfall. "
                        "Tidigare ändringar kan finnas kvar. "
                        "Nya skrivkommandon är spärrade tills resultatet "
                        "har kontrollerats manuellt. Försök inte igen automatiskt."
                    )
                elif summarize_guarded_outcomes(tool_outcomes) == "partially_completed":
                    answer = (
                        "Flerkommandot stoppades efter att minst ett steg "
                        "hade genomförts. Tidigare ändringar kan finnas kvar. "
                        "Kontrollera resultatet innan du försöker igen."
                    )
                else:
                    answer = (
                        "Verktygsåtgärden stoppades av säkerhetskontrollen. "
                        "Säg hela kommandot igen om det fortfarande ska köras."
                    )
                # No model output and no speculative streaming token
                # may present an unexecuted action as completed.
                if (on_chunk is not None and not delayed_memory_feedback
                        and not self._voice_stop_requested(_voice_plan_verifier)):
                    on_chunk(answer)
                return self._finalize_response(
                    user_message,
                    answer,
                    tool_names,
                    tool_results,
                    tool_plan=tool_plan,
                    pending_intermediate_results=pending_intermediate_results,
                    streamed=False,
                    tool_outcomes=tool_outcomes,
                    on_finalized_chunk=callback,
                    voice_plan_verifier=_voice_plan_verifier,
                )

            stream = getattr(
                self.llm,
                "chat_stream",
                None,
            )

            if not callable(stream):
                answer = self.llm.chat(
                    messages,
                    timeout=300,
                )

                if (on_chunk is not None and answer and not delayed_memory_feedback
                        and not self._voice_stop_requested(_voice_plan_verifier)):
                    on_chunk(answer)

                return self._finalize_response(
                    user_message,
                    answer,
                    tool_names,
                    tool_results,
                    tool_plan=tool_plan,
                    pending_intermediate_results=(
                        pending_intermediate_results
                    ),
                    streamed=False,
                    tool_outcomes=tool_outcomes,
                    on_finalized_chunk=callback,
                    voice_plan_verifier=_voice_plan_verifier,
                )

            chunks = []

            for chunk in stream(
                messages,
                timeout=300,
            ):
                # Never send another streamed voice chunk after Stop.
                if self._voice_stop_requested(_voice_plan_verifier):
                    break
                value = str(chunk or "")

                if not value:
                    continue

                chunks.append(value)

                if (on_chunk is not None and not delayed_memory_feedback
                        and not self._voice_stop_requested(_voice_plan_verifier)):
                    on_chunk(value)

            answer = "".join(chunks)

            return self._finalize_response(
                user_message,
                answer,
                tool_names,
                tool_results,
                tool_plan=tool_plan,
                pending_intermediate_results=(
                    pending_intermediate_results
                ),
                streamed=True,
                tool_outcomes=tool_outcomes,
                on_finalized_chunk=callback,
                voice_plan_verifier=_voice_plan_verifier,
            )

    def _remember_conversation_turn(self, user_message, answer):
        if self.max_conversation_turns <= 0:
            self.conversation_history = []
            return

        self.conversation_history.extend(
            [
                {
                    "role": "user",
                    "content": user_message,
                },
                {
                    "role": "assistant",
                    "content": answer,
                },
            ]
        )

        max_messages = self.max_conversation_turns * 2

        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    def clear_conversation(self):
        with self._response_lock:
            self.conversation_history = []
            self.intermediate_results.clear()

# MyAI VENTUNO Q – faktisk skrivskyddad smoke-förkontroll, 2026-10-19

## Låst testversion

`d28165c1cad81f8b4308ac7355a3fdfd81334986` – exakt testad source på DRAFT PR #349, oförändrad och utcheckad som detached HEAD på kortet i en separat tillfällig katalog. Hostad ARM64-kodsvit för denna source: https://github.com/Harrokk/Myai/actions/runs/39190171714 (SUCCESS, 4247 passed, 7 skipped) och signerägt UID-replayintegrationstest https://github.com/Harrokk/Myai/actions/runs/39190171681 (SUCCESS).

**Observera:** orkestrerings-workflowen som skapade själva read-only-runnen har **annan** commit `4e25c395cbca551ce0325f2dda1d68c8a47ae982`, eftersom den lägger till testinstrumentering på en annan DRAFT-gren. Git checkouten på enheten bevisades i jobbloggen vara exakt **låst source-SHA** enligt ovan.

## Nytt faktiskt fysiskt VENTUNO-resultat (skrivskyddat)

**GitHub Actions-run:** https://github.com/Harrokk/Myai/actions/runs/39215347361

- Tid enligt GitHub: **2026-10-19 07:20 UTC** (09:20 svensk tid, CEST).
- Jobb: `117937780685`.
- GitHub-status: **SUCCESS**. Runner: `ventuno-q` (självhostad ARM64, runner group `Default`), verklig köranvändare `arduino`, inte root.
- Exakt testkälla: `d28165c1cad81f8b4308ac7355a3fdfd81334986`, ren detached checkout under `RUNNER_TEMP`; tillfälliga testfiler borttagna i slutet.
- `scripts.ventuno_physical_pilot_gate --board-readonly` gav:
  - `status=board-readonly-preflight-passed`
  - `source_exact_sha=true`
  - `source_config_default_off=true`
  - `active_production_profile_default_off=true`
  - `board_preflight_included=true`, `board_preflight_passed=true`
  - `board_readiness_reason=ready-for-separate-consented-dialogue-test`
  - `ready_for_separate_human_consent=true`
  - `model_loaded=false`, `speaker_opened=false`, `physical_recording_attempted=false`, `npu_tested=false`, `production_changed=false`
  - `recording_authorized=false`, `playback_authorized=false`, `needs_new_one_shot_audio_consent=true`.
- Det innebär att den fysiska maskinen enligt den befintliga spärren var ARM64, hade aktiva MyAI- och GenieX-tjänster, åtkomlig USB capture + playback och **minst 8 GiB MemAvailable samt 3 GiB tillfällig ledig disk**. Den sanerade `pilot_gate` lämnar inte exakt RAM-/diskvärde, bara tröskelresultatet.
- `scripts.ventuno_usb_audio_inventory` gav `status=usb-capture-and-playback-pcm-detected`, USB-ljudkort 1, capture och playback på ALSA-par `[1,0]`, båda motsvarande device nodes `accessible=true` och `character_device=true`. `microphone_recorded=false`, `speaker_playback_started=false`, `usable_audio_signal_verified=false`, `services_modified=false`.

## Särskild säkerhetsbegränsning – INTE godkänd

Den faktiskt körda lokala `scripts.ventuno_runner_uid_acl_preflight --local-readonly` gav:

- `status=blocked_local_runner_privilege_preflight`.
- `bounded_source_metadata_complete=false`
- `preliminary_posix_dac_checks_passed=false`
- `distinct_account_and_group_candidate=false`
- `legacy_runner_unit_inactive_disabled_candidate=false`
- `expected_hardened_unit_properties=false`
- `runner_service_or_files_modified=false`
- `github_runner_group_and_historical_refs_verified=false`
- `production_deployment_authorized=false`.

**VIKTIGT:** GitHub-jobbets SUCCESS avser att den skrivskyddade diagnostiken genomfördes utan driftändringar; det **betyder inte** att runnerns isolering eller produktionssäkerheten är godkänd. Verkliga Linux-UID/ACL/sudo och GitHub runner groups/historiska branch-tillgångar återstår. Att runnern kunde köra ett uttryckligen begärt metadatajobb är inte ett nytt, generellt godkännande för ytterligare jobb.

## Nästa testgrind

Det **första kontrollerade ljud-smoke-testet** kan nu planeras utifrån ett färskt godkänt grundläggande board metadataresultat, men det kräver:

1. Fysisk operatör vid VENTUNO, tydlig stop-/rollback-rutin och kontroll av aktuell USB-anslutning (kan omnumreras efter omstart).
2. Ett **nytt explicit engångsgodkännande för inspelning och låg ljuduppspelning** – dagens tillstånd gällde endast read-only metadata.
3. Kort svensk testfras → STT → **en** lokal LLM-fråga → låg TTS endast om STT svarar rätt. Första fel stoppar testkedjan; ingen automatisk repetition eller persistenta konfigurationsändringar.
4. Fortsatt **NO-GO** för full NPU-profilerings-/strömavbrottstest, privilegierad CI-serviceinstall, produktionsnyckelrotation, GitHub runner-omregistrering eller självmodifierande MyAI.

**Inga ändringar av produktionens MyAI-inställningar, tjänster eller data och ingen `main`-merge har gjorts av denna kontroll.**

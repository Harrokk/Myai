# Granskning av de åtta flaggade kodställena – DRAFT

**Datum:** 16 oktober 2026. Syfte: utföra riktade **syntetiska** tester och en strukturell granskning av de åtta känsliga anropen som hittats av `scripts/static_repository_audit.py`. De ligger inte automatiskt bakom en bugg; de är markerade därför att AST-granskningen hittar anrop av `subprocess.Popen` eller `exec`.

## Inventering och separat testtäckning

| # | Kodställe | Risk och kontroll | Regressionstest |
| --- | --- | --- | --- |
| 1 | `core/voice_stt_persistent.py::_spawn` – `subprocess.Popen` | **Produktion:** startar en isolerad STT-arbetare. Måste ha offline-miljö, ingen shell, nytt process-session, privata pipelines och undertryckt stderr. Testas enbart med syntetisk Python-arbetare; **ingen riktig Whisper-modell** | `tests/test_voice_stt_persistent.py` – normal återanvändning, timeout, krasch, reaping, infekterad IPC, failed spawn |
| 2 | `tests/test_ventuno_whisper_base_swedish_comparison.py::_pure_phrase_metrics` – `exec` | Kontrollerat test som exekverar den **incheckade konstanten** `compare._METRIC_SOURCE`, aldrig användartext eller nedladdat innehåll | `tests/test_ventuno_whisper_base_swedish_comparison.py::test_private_metrics_compute_only_categorical_distance` |
| 3 | `tests/test_voice_process_census.py::_synthetic_parent` – `subprocess.Popen` | Skapar en kortlivad testsession och eventuell syntetisk barnprocess som avslutas av `finally` | `test_recognisable_older_process_vetoes_prepare_and_release`, `test_recognised_process_descendants_with_unrelated_args_veto` |
| 4 | `tests/test_voice_process_census.py::test_unrelated_synthetic_python_process_not_inaccurately_attributed` – `subprocess.Popen` | Negativ kontroll: orelaterad Python-process ska **inte** felklassas som MyAI, stängs alltid i `finally` | Testet med samma namn |
| 5 | `tests/test_voice_stt_process.py::test_environment_is_forced_offline_and_does_not_inherit_secrets` – `subprocess.Popen` | Barn-process via injicerad `popen`; verifierar att hemliga tokens/proxyvariabler inte ärvs | Testet med samma namn |
| 6 | `tests/test_voice_stt_process.py::test_one_shot_child_resource_env_is_child_only_and_default_off` – `subprocess.Popen` | Verifierar barns CPU-/minnesgränser utan att ändra förälderns miljö | Testet med samma namn |
| 7 | `tests/test_voice_stt_process_group.py::_leader_with_helper` – `subprocess.Popen` | Syntetisk ledare/barn där även frikopplad hjälpprocess ska avslutas, ingen riktigt röstverktyg | `test_helper_is_killed_after_stt_leader_already_exited`, `test_helper_and_active_parent_are_killed_together` |
| 8 | `tests/test_voice_stt_rlimit_denial.py::test_oneshot_parent_reaps_worker_rejected_during_resource_bootstrap` – `subprocess.Popen` | Syntetiskt barn nekas resursgränser **före** modellimport och måste återtas säkert | Testet med samma namn, RLIMIT_CPU och RLIMIT_AS |

## Kontroller

- En ny källa `scripts/ventuno_eight_sensitive_calls_review.py` använder `ast` för att kräva **exakt åtta** identifierade känsliga anrop med förväntade funktionsnamn. Nya/ändrade anrop eller borttagna filer ska ge fail-closed.
- Produktions-STT:s Popen måste fortsatt ha `cwd="/"`, `start_new_session=True`, stdin/stdout som pipes, stderr som `DEVNULL`, `env=offline_environment(...)` och inget `shell=True`. Detta är en strukturell spärr, inte bevis på att den faktiska maskinmodellen är säker.
- `exec` får bara använda den incheckade jämförelsemodulens fasta matematiska måttkälla. Testerna granskar en integritetsskyddad kategorisering av testfraser och producerar inga personliga transkript.
- Kör de befintliga regressionerna och den nya AST-spärren på GitHub-hostad Linux och VENTUNO Q ARM64 via **disponibla, exakt SHA-låsta testcheckouts**. Inga mikrofoner, ljuduppspelning, QAIRT/HTP, verkliga modellvikter, tjänstestopp eller driftsättningar.
- Väsentligt: statiska auditverktyget **fortsätter avsiktligt rapportera åtta manuella flaggor** eftersom koden fortfarande innehåller dessa anrop. Ny granskningsmatris betyder att de har **granskats och testats syntetiskt**, inte att farliga programanrop har tagits bort eller bevisats säkra för alla miljöer.
- Kvarvarande verkliga risker: systemd/barnprocesser som inte följer samma processgrupp, en riktig STT-modells CPU/RAM-beteende, verifierad hårdvaruåterställning och fysisk röstkvalitet. Dessa kan inte godkännas av syntetiska testfall.

## Beslutsgräns

Godkänd riktad CI på båda arkitekturerna plus granskning innebär att vi kan lägga undan de **åtta manuella granskningspunkterna i källkoden för den här DRAFT-versionen**, medan den verkliga hårdvarugrinden för den produktionsnära STT-processen fortfarande kräver ett kontrollerat fysiskt test. Det innebär **inte** att koden ska driftsättas eller att alla riskflaggor bör filtreras bort ur auditrapporten.

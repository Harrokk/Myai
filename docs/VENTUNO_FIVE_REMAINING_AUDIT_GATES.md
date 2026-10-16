# MyAI – sista fem revisionspunkterna inför fysisk VENTUNO-testning

**2026-10-16.** Denna DRAFT-version baseras på den tvåföräldersintegrerade PR #240. **Den är inte produktionsinstallerad.** Kontrollerna får inte registrera ljud, spela upp, läsa privata konversationer, starta modellvikter, slå på röst eller profilera NPU/HTP. Alla sådana moment kräver separata godkännanden.

## 1. ARM64 röstpaket, isolerad riktig installation och importkompatibilitet

Den incheckade `requirements-voice-arm64-hashed.lock` och `config/voice_arm64_cp312_wheels.lock.json` innehåller 28 verkligt nedladdade, hashlåsta CPython 3.12/ARM64-hjul. Installerad produktions-venv saknade 4/4 huvudbibliotek i tidigare inspektion.

Ny testkedja kör **endast i `$RUNNER_TEMP/myai-two-pass-audit.*/.voice-abi-venv`** på self-hosted ARM64 och slutar med att radera hela temporära testcheckouten. Enhets- och minnesreserv kontrolleras innan venv skapas; pip använder binära paket `--require-hashes` och ingen cache. Korta separata importprocesser testar Python/native ABI för `numpy`, `ctranslate2`, `av`, `faster_whisper`, `sounddevice`, `webrtcvad` och `pyttsx3`. Modeller laddas **inte**, inga device handles öppnas av vår kod, och importprocesserna får nätverk OFF samt begränsade CPU-trådar.

En lyckad import är **inte** bevis för korrekt STT-prestanda, PortAudio routing, fungerande mikrofonljud eller stabila native backend-trådar under belastning. Native drivrutins-/hårdvarutester är fortfarande kvar.

## 2. Syntetisk komplett röstkedja och processkrasch

Hostad CI tar med `test_voice_pipeline`, `test_voice_session`, `test_ventuno_usb_dialogue_once` och befintliga STT-testsystem. Ny `test_ventuno_voice_trial_crash_cleanup` dödar ett helt syntetiskt Python-barn efter att barnet skrivit en *icke-personlig* PCM-lik testfil i separat temporär katalog. Testet bekräftar att testkatalogen tas bort av övervakande förälder efter barnkrasch, och inga filer hamnar utanför projektets disponibla testrot.

Observera begränsningen: `SIGKILL` mot **föräldern** eller verkligt strömavbrott kan lämna en disktempfil. Den garantin kräver separat file-system/tmpfs-design och verklig fysisk verifiering. Ingen automatisk upprepning av oktoberinspelningen får ske.

## 3. Effektiv inställning, minne, loggar och backend-återställning

`ventuno_voice_trial_DISABLED.json` är fortfarande **OFF** med egen SQLite-databas under `runtime/isolated_voice_trial/` och separat testlogs/health/heartbeat. In-memory-attestering via `runtime_safety_attestation` är konstruerad för framtida versioners samarbetsvilliga runtime-processer och kan validera endast fasta booleanska riskflaggor.

Den **redan körande produktionstjänstens** inställningar är ännu inte kryptografiskt verifierade. Vi får inte härleda dem från en filhash eller ett tidigare inhämtat MainPID. Inga riktiga minnen, testfraser eller permanenta logs får flyttas från provkatalogen till produktionen. Vill vi aktivera framtida separat VoiceSession krävs först granskad aktiv settings- och databasintegration samt ett explicit isolerat startfönster.

## 4. Kontroll av samtliga Actions – inte enbart fyra gamla `main`-filer

Fyra main-unika workflows är ersatta av inerta arkiv i den integrerade PR #240. Nya `ventuno_all_workflow_preflight` går igenom alla `.github/workflows` och hittar möjliga hårdvarukommandon och push-/manual-triggers. Om en effectful workflow kan starta automatiskt på kandidatgrenen ges **NO-GO**. Manuellt körbara gamla one-shots behålls i rapporten och kan **inte** tolkas som tidigare permanent användarsamtycke. Scan är en konservativ text-/source-inventering och ersätter inte full YAML-parser eller säkerhetsgranskning av uttryck/Actions.

En framtida kampanj ska köras från en specifik allowlist av nya, isolerade tester. Historiska effektfulla workflow_dispatch-kommandon får inte startas bara för att de finns.

## 5. Slutlig källa, releasebeslut och rollback

`ventuno_source_release_readiness` kräver: giltig exakt HEAD SHA, ren Git-worktree, verifierad main + DRAFT #239 ancestry i **hela** Git-historien, karantän för fyra gamla main-jobs, inga automatisk-aktiva hårdvarujobb för kandidatgrenen, avstängd och exakt stage-konfiguration samt matchande 28-hjuls källfil/hashes.

Ett helt grönt source-resultat säger uttryckligen: `source-candidate-consistent-but-not-deploy-authorized`. Fysiska sign-off-fält är oförändrat **false**; ingen auto-merge eller deployment från rapporten.

### Praktiskt stop-/återställningsprotokoll för senare fysisk testdag

1. Läs-only gate på exakt test-SHA: source-only, USB + volym + RAM/disk/temperatur, aktiva GenieX/MyAI/runner, och rätt säkert testprofil.
2. Kontrollera lokal konsol/oberoende återställning **innan** någon aktiv NPU-profilering eller störande åtgärd. Dokumentera status för systemd-enheterna utan att exponera hemligheter.
3. Nytt uttryckligt engångssamtycke krävs före *varje* verklig ljudinspelning. Ställ in låg uppspelningsvolym, en godkänd kort svensk testfras, Stop på första fel, och noll automatiska retries.
4. Kör röstprovet med endast read-only verktyg och disponibel stage-databas. Verifiera att alla underprocesser är avslutade och att inga privata WAV-, SQLite WAL- eller loggfiler finns kvar efter avveckling. Vid okänt write-status: ingen automatisk journalupplåsning.
5. NPU kräver **ett separat** underhållsfönster och full QAIRT/HTP-kompatibilitet (inklusive per-operator mätverktyg, modell och fysisk återställning). Den här DRAFT-testningen kör inte NPU.
6. Efter varje körning: verifiera tjänster, källversion, USB-anslutning och profilflaggar oförändrade; meddela stopp om inte hela kedjan är säker.

### Versionsmärkning

Baslinje: PR #240 slut-SHA `e16a64ea8cdd6cc026c5eb21ba8b8b89b02f9d8d`. Ny DRAFT-gren ska testas på sin **egen slutliga SHA**; tidigare godkända siffror gäller inte automatiskt en ny commit. Publicera faktiska godkännanden, blockerande fel och kvarvarande fysiska gränser i PR-checkpoint.

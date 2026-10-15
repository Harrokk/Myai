# MyAI — riktad dubbelgranskning av isolerad STT-process

**Datum:** 2026-10-15 · **Underlag:** PR #221 + efterföljande STT-säkerhetsändringar · **Omfattning:** röst-STT-processerna och relevanta test-/CI-anrop, **inte** en fullständig projekt-audit. Ingen driftsättning är genomförd.

## Pass 1 — logik, livscykel och konkurrerande händelser

Granskade `core/voice_stt_persistent.py`, `core/voice_stt_process.py`, `core/voice_stt_process_group.py`, `core/voice_stt_bounded_io.py`, `core/voice_session.py` samt tillhörande regressionsprov.

**Fynd A — avbruten cleanup kunde göra en osäker process återanvändbar:** `_release()` fångade tidigare `Exception`, men inte `KeyboardInterrupt`/`SystemExit`. Om reap avbröts kunde `_worker` fortfarande finnas samtidigt som `_cleanup_required` var falskt. Nu fångas även ett avbrott, tidigare processreferens behålls, cleanup markeras som ofullständig och framtida `transcribe()`/`resume()` stoppas till dess att `close()` lyckas. **Verifiering:** injicerad `KeyboardInterrupt` i process-reap med verklig men syntetisk Linux-STT-child, följt av misslyckad nästa förfrågan och uttrycklig lyckad cleanup-retry.

**Fynd B — överbliven svarsruta kunde förväxlas med nästa yttrande:** den persistent arbetaren hanterade en längdprefixerad JSON-ruta och hade ingen extra kontroll av bytes som låg färdiga efter rutan. Ett felaktigt barn kunde skicka två kompletta svar för samma ljud. Ny icke-blockerande gränskontroll tittar efter *redan buffrade* extra svarsbytes efter varje godkänd ruta samt före varje nytt PCM-utskick. Om bytes finns avvisas svaret och den ägda processen städas; EOF efter en giltig slutruta tolereras. **Verifiering:** en syntetisk child skickar två fullständiga svar i samma flush; inga svar godkänns och nästa yttrande kräver ett nytt rent barn.

**Kvarstående livscykelbegränsningar:** gränskontroll av redan buffrade bytes är inte kryptografisk bindning mellan ljud och transkript. En illvillig child kan tidsstyra felaktiga svar så att den kontrollen inte upptäcker dem. Starkare bindning kan i framtiden införas med unik begärande-ID/nonce inuti ramen. Processgruppsstädning garanterar inte borttagning av hjälpprocesser som lämnar gruppen eller av Linux D-state. Hårda aggregatgränser över processer kräver separat cgroup-design.

## Pass 2 — sekretess, processstart och kodexekvering

Oberoende kontroll av statiskt flaggade känsliga anrop, argument, källa till körbar kod, miljö och test-isolering:

| Flagga | Fil | Bedömning |
|---|---|---|
| `subprocess.Popen` | `core/voice_stt_persistent.py` | **Produktionskod, kräver fortsatt manuell merge-review.** `persistent_argv` tillåter bara den incheckade arbetaren och validerade modellargument; ingen shell, `python -I`, en minimerad offline-miljö och separat barnprocessgrupp. Kan ändå inte garantera native FastWhisper-/FFI-säkerhet eller faktisk RAM-förbrukning. |
| `subprocess.Popen` (2 anrop) | `tests/test_voice_stt_process.py` | Syntetiska testbarn för env/cap och stdout; ingen produktionstilldelning, ingen riktig modell. |
| `subprocess.Popen` | `tests/test_voice_stt_process_group.py` | Syntetiskt hjälpbarn med 60s väntan i egen grupp för städningsverifiering; CI begränsar tid, inga produktionsservicekommandon. |
| `subprocess.Popen` | `tests/test_voice_stt_rlimit_denial.py` | Syntetisk barnprocess som avvisar rlimit innan modellimport; inga faktiska CPU/AS-ändringar på boarden. |
| `exec(compare._METRIC_SOURCE, namespace)` | `tests/test_ventuno_whisper_base_swedish_comparison.py` | Test av internt definierad metric-källsträng, inte användarlevererad text. **Behåll manuell granskning**, särskilt om strängens ursprung ändras framöver. |

**Sekretesskontroller:** strikta JSON-typer, konstanta användarfel, ingen rå ljudbytesdump, limiterad stdout och språk-/textschema. Separat testverifiering av sanerade `TimeoutError` respektive `OSError`; inga skrivningar till inställningar för root/runner/GenieX. Ingen extern användarkod får bli del av process-`argv` via den inbyggda voice-fabriken.

**Öppet:** `RLIMIT_AS` är *virtuell adressrymd* och inte RSS; `RLIMIT_CPU` mäter CPU-tid och inte realtid. Trösklar är default-off och verklig FasterWhisper-minnesprofilering kvarstår i gruppen `docs/PHYSICAL_PRESENCE_TESTS.md`. Ingen aktion från CI får slå på denna funktion i produktion.

## Samlad slutsats

Två konkreta kodfel åtgärdade i separat DRAFT PR med syntetiska regressionsprov. Statisk audit kan markera riskanrop men kan inte bekräfta driftsättningssäkerhet; de sex manual-review-flaggorna redovisas därför explicit, inte som automatiskt avklarade. **Inga** aktiva tjänster, root-privilegier eller fysiska modellkörningar berörs.

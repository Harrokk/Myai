# VENTUNO Q – isolerad röstprofil inför fysisk engångstestning

**Status:** Source-only staging, **AVSTÄNGD**. Denna profil aktiverar INTE ljudinspelning, ljuduppspelning, lokal STT, NPU eller full MyAI. Den får inte väljas som aktiv produktion av CI.

## Två explicita källprofiler

- `config/profiles/ventuno_q.json`: befintlig installerad produktionsprofil. Ändras inte.
- `config/profiles/ventuno_voice_trial_DISABLED.json`: extra **incheckad och avstängd** provprofil. Det krävs ett nytt, övervakat användargodkännande och en separat operatörsprocess innan något ljud får tas in.

`scripts/ventuno_isolated_voice_stage_contract.py` läser källversionen och den avstängda testprofilen, härleder normal MyAI-konfigurationsmerging med `core.config.DEFAULT_SETTINGS`, kräver **exakt överensstämmelse** med ett granskat tillåtelselista-kontrakt och kör `validate_settings(...require_ventuno_profile=True)`. Saknad/symlinkad/ogiltig/ändrad profil ger NO-GO. Ingen temporär fil, SQLite-databas eller modell skapas.

### Konfiguration som isoleras

- STT planeras för **Whisper Tiny CPU/int8** i **isolerad barnprocess**, persistent modell avstängd, timeout 45 s. Ett CPU RLIMIT-förslag 30 s, men ingen spekulativ virtual memory `RLIMIT_AS` eftersom det kan förstöra minnesmappade native bibliotek. Detta är en plan, **inte testad modell/prestanda**.
- Röst `enabled=false`, `tts_enabled=false`, `handsfree_enabled=false`, `llm_streaming_enabled=false`. Ingen automatisk inspelning eller output.
- Minne använder `runtime/isolated_voice_trial/memory.db`. `auto_assess_enabled`, `auto_save_enabled`, `review_queue_enabled`, `lifecycle_enabled` och `permanent_delete_enabled` är `false`. Detta blockerar automatiska minnesändringar; isolering kräver dessutom att själva operatörens checkout/körplats är disponibel och **inte** den körande produktionens projektkatalog.
- Audit, error, runtime/heartbeat, health, GenieX-watchdog och stability-rapporter pekar på separat `runtime/isolated_voice_trial/`. `files` och Excel-skrivning, kamera, plats, Bluetooth-trusted terminals, selfdev, hw-watch, MCU RPC och service-restart hålls OFF.
- Testprofilen har fortfarande GenieX som LLM-provider; **inget LLM-anrop görs av profileringsgrinden**.

### Avsiktliga spärrar som återstår

1. Verklig produktions-venv på VENTUNO visade **0/4** nödvändiga ordinarie röstbibliotek (`sounddevice`, `webrtcvad`, `faster_whisper`, `pyttsx3`) i read-only kontroll. Inga paket installeras här. Versions-/ABI-kompatibel staging-venv med licens-/drivrutinsgranskning behövs före det normala ljudtestet.
2. `MYAI_SETTINGS` och aktiv systemd-`ExecStart` har ännu inte attesterats med sanerad aktiv processproveniens. Läsning av en installerad OFF-profil bevisar inte vilket dokument en redan körande process faktiskt laddade.
3. Den här testprofilen är INTE en aktiverad runtime och ger INTE tillstånd till annan modell, ljud, NPU/HTP, självmodifiering eller fysisk belastning.
4. En dedikerad **fysisk** testoperatör måste fortfarande godkänna en enskild begränsad fångst och uppspelning efter ny aktuellt USB/säkerhetspreflight; konfigurations- och minnesavgränsning ska vara bekräftad.

## Reproducerbar read-only kontroll

```sh
python3 -B -m scripts.ventuno_isolated_voice_stage_contract
python3 -B -m pytest -q tests/test_ventuno_isolated_voice_stage_contract.py
```

Utdata är endast en tillåten statisk status plus booleaner. Källkodsprofilen kan inte användas för att smygaktivera `--record` eller `--install`; inga sådana flaggor finns. Körningar i GitHub-jobb görs på **exakt Git-SHA i disponibel checkout**, inte på /home/arduino/MyAI och ändrar inte systemd.

**Viktig återstående integrationsprincip:** en fullt grön staging-profil visar endast konfigurationens integritet; all fysisk ljud- och prestandafunktion är fortsatt opåvisad.

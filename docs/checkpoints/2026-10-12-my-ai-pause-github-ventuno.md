# MyAI – PAUSAD, GitHub och VENTUNO Q

Datum: 2026-10-12. Avsikt: avsluta arbetet, bevara ett återupptagbart läge.

## Kod och versionshantering

Repository: Harrokk/Myai
Utvecklingsgren: dev/routing-boundary-followup
Senaste fullständiga experimentdokumentation: docs/checkpoints/2026-10-12-piper-alma-whisper-swedish-stt.md
Bekräftad dokumentationscommit före pausen: ef347481d69ae0679c41d0c53bc293a759e6fa88
Pausfilen finns på utvecklingsgrenen. Ingen merge till main görs vid pausen.

## VENTUNO Q – bekräftat läge

Hårdvara: Arduino VENTUNO Q 16 GB RAM, USB-mikrofon och USB-högtalare.
Produktionsmotor: GenieX (Qwen3 via Qualcomm). MyAI och GenieX har varit aktiva och lämnades oförändrade av de senaste testkörningarna.
Ollama: officiell ARM64 v0.34.0, Qwen3 0.6B installerad under /home/arduino/.local/opt/myai-ollama/v0.34.0. Testad med verkligt lokalt MyAI-anrop; Ollama-servern lämnas inte permanent igång.
Produktionsröst: voice.enabled=false, tts_enabled=false, handsfree_enabled=false. Ingen automatisk omkoppling, återstart eller handsfree.
Whisper Tiny/Base, eSpeak och Piper Alma: senaste experimenten gjordes i tillfälliga separata miljöer och rensades efter varje test. Ingen ny STT-modell är permanent driftsatt.

## Senaste viktigaste tekniska resultat

Verklig mikrofon -> Whisper -> Ollama -> högtalare är ännu INTE godkänt end-to-end. Kontrollerade mikrofonförsök fångade ljud men Whisper gav icke godkänd text; ingen fråga skickades vidare till Ollama i dessa försök. Ingen användarinspelning eller transkription sparades.

Syntetisk svenskkontroll ”Vad heter du?”:
- eSpeak NG + Whisper Tiny/Base, två hastigheter och beam 1/5: 0 av 8 korrekta.
- Piper Alma (sv_SE, pinnad och SHA256-kontrollerad) + samma Whisper Tiny/Base-matris: 8 av 8 korrekta.
- 120/120 regressionstester godkända på VENTUNO för Piper-jämförelsen.
- Bekräftad körning: https://github.com/Harrokk/Myai/actions/runs/38284679674
- Jämförelsen tyder på att eSpeak-tal var ett olämpligt syntetiskt testprov. Den bevisar INTE att mänskligt svenskt tal nu fungerar säkert i mikrofonen.
- Piper är ej permanent installerad, endast testad i en isolerad miljö.

## Nästa steg när användaren säger ”Fortsätt MyAI”

1. Börja med att läsa denna checkpoint och docs/checkpoints/2026-10-12-piper-alma-whisper-swedish-stt.md.
2. Bekräfta att VENTUNO Q:s MyAI och GenieX fortfarande är aktiva och att produktionsröst är avstängd. Undvik onödiga tjänstomstarter.
3. Nästa rekommenderade utvecklingssteg: testa ett rättighetsverifierat naturligt svenskt talprov av samma fråga mot Whisper Tiny, helt utan fysisk mikrofon.
4. Behåll Whisper Tiny som utgångspunkt; uppgradera inte till Base enbart på dessa resultat.
5. Vid senare önskemål om fysisk rösttest: inhämta nytt uttryckligt engångsgodkännande, ge hörbar startsignal, begränsa volym och inspelning samt spara inga råtranskript eller ljud. Återanvänd aldrig tidigare ljudauktorisering.
6. Behåll GenieX som produktionsstandard och installerad Ollama som separat valbar motor, med fallback avstängd tills separat validering.

## Pausregler

Inga fortsatta modellkörningar, inspelningar, schemalagda jobb, automatiska omstarter eller inställningsändringar. Denna text får kopieras till användarens separata checkpointkatalog på VENTUNO Q som en ren statusfil; kopieringen ändrar inga produktionsfiler och startar inga modeller.

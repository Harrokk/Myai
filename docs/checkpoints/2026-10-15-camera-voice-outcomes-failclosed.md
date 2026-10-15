# MyAI kontrollpunkt – kamera-, video- och bildruteverktyg rapporterar fel säkert vid röststyrning

Datum: 2026-10-15. Stacked utvecklingsgren `dev/ventuno-camera-outcome-voice-safety-20261015` ovanpå [PR #184](https://github.com/Harrokk/Myai/pull/184). **DRAFT**, ej mergad, installerad eller driftsatt.

## Utgångsläge

- [PR #184 isolerad ARM64 CI #38687777564](https://github.com/Harrokk/Myai/actions/runs/38687777564): **2121 passed, 15 skipped**, statisk källkod-/privacy-audit **PASS, 0 blockerande**. Hela VENTUNO/GenieX-produktionen oförändrad.
- PR #184 införde explicit `ToolOutcome(success, value)`, `{"success": false}` och en per-verktyg opt-in-lista `result_failure_prefixes` i det **guardade röstflödet**, med stegstatus `succeeded|failed|blocked` och helplanstatus `completed|partially_completed|failed|not_started`. Registry-policyn ingår i privat sessions-HMAC. Legacy textverktyg behåller tidigare resultatform.
- Kameraverktygen `camera_capture`, `camera_record_video`, `camera_sample_video_frames` och `camera_stream_status` fångade redan undantag, formaterade fel till **vanliga strängar** och saknade explicit röst-`safety`-metadata. Kamera- och videoinspelning skriver bestående filer och stream-test aktiverar lokal kamerahårdvara, därför är det fel att behandla dem som vanliga läsverktyg.

## Kodändring (endast verktygsregister; inte ett nytt kameratest)

- `modules/camera/capture.py`: `camera_capture` får `effect=write`, `voice_confirmation_required=True`, samt det **exakta** befintliga felprefixet `Kamerabilden kunde inte tas:`.
- `modules/camera/video.py`: `camera_record_video` får motsvarande skriv-/bekräftelsepolicy och prefixet `Videoinspelningen misslyckades:`.
- `modules/camera/video_frames.py`: `camera_sample_video_frames` får skriv-/bekräftelsepolicy och prefixet `Bildrutor kunde inte plockas ut ur videon:`.
- `modules/camera/stream.py`: `camera_stream_status` får `effect=local_capture` och separat explicit `voice_confirmation_required=True`, eftersom det öppnar kameran trots sitt statusnamn. Två exakta felprefix används: `Kamerastream-testet misslyckades:` och `Kamerastream är avstängd.`. Ett avstängt stream-test klassas alltså inte som en lyckad åtgärd.
- Varken `camera_capture()`, `record_clip()`, `run_bounded_stream()` eller `extract_video_frames()` har gjorts om; de existerande publika **svenska textsvaren bevaras**. Endast den skyddade röstmotorn klassificerar dessa explicita felsträngar som misslyckade steg, sanerar eventuella privata detaljer och stoppar senare verktyg.
- MyAI:s tidigare 3-av-3-STT-instanser, 2-av-3-exakt majoritet vid högrisk, separat röstsäkerhetsbekräftelse och HMAC-bunden dispatch gäller nu även dessa kamera-/videofunktioner. Ingen kamera aktivieras när ett sådant delsteg saknar godkänd röstplan.

## Testbevis

- [GitHub-hosted x86 synthetic-only #38688402758](https://github.com/Harrokk/Myai/actions/runs/38688402758): **46/46 tester PASS**. Helt fejkade `capture_from_settings`, `record_video_from_settings`, `sample_latest_video_from_settings` och `run_bounded_stream`. Inga `cv2`-moduler laddas för verklig kamerakörning och ingen kamera, video, mikrofon eller fysisk filskrivning sker.
- För varje av fyra moduler verifieras röstbekräftelsekrav, fail-closed vid nekad verifierare, sanering av felresultat och fail-stop innan senare fake-`workspace_write`. Positiv syntetisk formatstatus är fortsatt framgång, kamerastream disabled är ett tydligt misslyckande, och ändrad failure-policy ogiltigförklarar privat HMAC. Ett integrerat `MyAICore.respond_voice()`-test bekräftar att ett kamerafel inte får språkmodellen att påstå att även nästa skrivsteg är slutfört.
- Ordinarie source-only ARM64 CI på **exakt slutlig PR-head** måste vara SUCCESS innan PR kallas fullständigt verifierad.

## Viktiga gränser

- Säkerhetsklassningen gäller användarkommandon via den hårdnade **röstvägen**. Textvägens tidigare verktygsbeteende och röstprofiler som stänger av högriskbekräftelse utgör separata policygränser; den faktiska röst-dispatchen kräver fortfarande korrekt bindning.
- En kamerakörning som rapporterar `failed` kan ha hunnit skapa delvis sparad bild/video. PR #184:s `attempted=True` och partiell status är avsiktligt konservativ: inga garanti om rollback eller oförändrade filer.
- Dessa enbart syntetiska tester verifierar **inte** reell kamera-/mikrofonfunktion, bildkvalitet eller fysisk åtkomst. Kameran är fortsatt en framtida opt-in-modul och ska inte aktiveras på VENTUNO genom denna PR.
- Inga `sudo/apt`, tjänste-/systemd-ändringar, USB-ljud, lokala bildfiler, firmware, grupper/ACL/udev, GenieX, HTP/NPU/QNN-inferens, Qualcomm AI Hub-konto/QAIRT molnjobb/modelluppladdning, produktionsinstallation eller PR-merge har utförts. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk secret-purge/GitHub Support-cache kvarstår separat releaseblockerare. HTP-v75 runtime- och QAIRT 2.46 live-kompatibilitet är obevisad.

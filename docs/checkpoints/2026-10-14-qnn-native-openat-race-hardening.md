# MyAI kontrollpunkt – filhandtagsbaserad verifiering av QNN-utdata

Datum: 2026-10-14. Separat DRAFT-gren `dev/ventuno-qnn-output-openat-failclosed-20261014` på [PR #176](https://github.com/Harrokk/Myai/pull/176). **Ej mergad, installerad eller driftsatt.**

## Utgångsläge och upptäckt risk

- [PR #176 ARM64 CI #38629843669](https://github.com/Harrokk/Myai/actions/runs/38629843669): **2024 passed, 15 skipped**, statisk integritetsgranskning PASS, 0 blockerande fynd.
- [PR #176 riktig VENTUNO metadata #38629736575](https://github.com/Harrokk/Myai/actions/runs/38629736575): QNN CPU-bibliotek `/usr/lib/libQnnCpu.so` verifierades som vanlig AArch64-fil ägd av QAIRT `qairt-libs`. **Ingen ny CPU- eller HTP-körning** utfördes.
- Både framtida syntetiskt QNN CPU-referenstest och HTP-diagnostik delar nu `scripts/ventuno_qnn_native_result_attestation.py`, som korrekt jämför högst en 64-byte native output mot tidigare verifierad SHA-256 CPU-referens.
- Den tidigare attestorversionen använde `Path.is_symlink()`, `Path.is_file()` och `Path.stat()` **före** `Path.read_bytes()`. Därmed fanns en möjlighet att exempelvis `result.raw` eller `Result_0` byttes till en symbolisk länk efter kontrollen men innan filen öppnades (**TOCTOU-race**). `read_bytes()` följer då länken.
- Detta var en **kodrisk i en tillfällig isolerad QNN-arbetskatalog**, inte ett konstaterat intrång eller bevis för att historiska HTP-resultat manipulerats.

## Fail-closed-fix

- Inga QNN-kommandon. Den gemensamma attestor-helpern öppnar nu först rotkatalogen, sedan `results`, sedan `Result_0` med `os.open` och `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`; underkataloger öppnas **relativt till redan öppnad katalog-fd**. Byte av namnet under kontrollen kan inte dirigera om fd till en godtycklig annan plats.
- `os.scandir(folder_fd)` enumererar högst **24 entries** utan att materialisera en obegränsad fillista. Exakt **en** fil med `.raw`-ändelse måste hittas.
- Råfilen öppnas med `O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, relativt öppnad katalog-fd. `fstat` kräver vanlig fil och exakt **64 bytes**. Läsningen är begränsad till **65 bytes** även om filen växer efter första `fstat`; andra `fstat` nekar ändrad storlek och inode.
- Alla fd stängs i `ExitStack`. Felklassificering bevarar de tidigare publika statuserna för fel storlek, trasiga/otillåtna kataloger, symlänkar, tomt resultat och tvetydiga filer. Ingen fildata, sökväg eller digest läcker i rapporten.
- SHA-match mot samma verifierade CPU-referens är fortfarande bara **utdataparitet**, inte bevis för HTP-operatorplacering, NPU-verifiering eller firmware-/processdomänkompatibilitet.
- Sex nya **enbart syntetiska** regressionstester simulerar utbyte av råfil med länk precis före `open`, katalogutbyte, FIFO (utan blockering), läsbudget 65 bytes, storleksändring under läsning och filnamnsbyte efter öppning (redan öppnad inode används).

## Verifiering och fortsatta gränser

Fullständig isolerad ARM64 CI körs automatiskt vid commit och utvärderas på exakt senaste PR-head innan resultatet får rapporteras som godkänt. Inga verkliga QNN CPU-/HTP-modellkörningar eller läsningar från någon privat träningsdata ingår.

Ingen `sudo`, paketinstallation, firmware, grupp-/udev-/ACL-ändring, tjänsteomstart, GenieX-/Ollama-påverkan, ljud/kamera, API-token, Qualcomm-molnjobb, modelluppladdning, merge eller driftsättning. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk sekretessrensing / GitHub Support cache kvarstår separat releaseblockerare.

**HTP-frågan är fortsatt öppen:** QAIRT 2.46 i autentiserad Qualcomm Cloud-katalog, V75-specifik operatörsacceptans, DSP process domain och faktisk NPU-placering är ännu inte verifierade.

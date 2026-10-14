# MyAI – nästa ACL-kontroll: effektiv DMA-heap-rätt för GenieX

Datum: 2026-10-14. Separat utvecklingsgren efter PR #157. **Inget installerat eller mergat.**

## Redan verifierat på riktig VENTUNO

- [PR #157 CI, run 38592965020](https://github.com/Harrokk/Myai/actions/runs/38592965020): **1871 passed, 14 skipped**, static source/privacy audit PASS med 0 blockerande fynd. Testerna kördes i isolerad runner-arbetskatalog.
- [PR #157 real device metadata, run 38592965661](https://github.com/Harrokk/Myai/actions/runs/38592965661): DMA-heap har POSIX ACL-xattr; runnerns effektiva skrivåtkomst är tillåten fast vanliga DAC-bitarna nekar. Både runner och GenieX saknar effektiva Linux-capabilities. Secure CDSP xattr rapporterade `not_exposed`, vilket inte bevisar att alla LSM-regler är frånvarande.
- /lib/udev/rules.d och /usr/lib/udev/rules.d är samma katalog-inod. Tidigare `scan_complete=false` kan inte tillskrivas denna alias säkert, eftersom föregående skanner redan deduplicerar samma inod.
- Ingen faktisk GenieX `open(2)`, FastRPC-session eller HTP-beräkning har verifierats av metadatakontrollerna.

## Vad denna gren gör

- `scripts/ventuno_dma_acl_effective_readonly.py` kontrollerar endast den redan kända character device `/dev/dma_heap/system` via lstat och xattr (ingen device-open). POSIX ACL-xattr version 2 läses med max 4096 byte och parsen kräver godkända taggar, rätt struktur, unika objektposter, tillåtet rwx-område och mask vid namngivna poster.
- Baserat på ACL och redan verifierad GenieX FSUID/FSGID/grupper returneras **endast booleska läs- och skrivrättigheter**, eller okänt vid fel. Samma beräkning görs för runnern och jämförs med os.access. Ingen ACL-rawdata, UID/GID, PID, sökvägar eller hemliga värden exporteras.
- Syntetiska tester kontrollerar POSIX ACL owner/named-user/group/mask/other, invalid format, högsta storlek, datautlämning och icke-device refusal.
- En separat exakt-commit GitHub Actions-körning är strikt metadata-only och använder temporär check-out utan sudo, QNN, HTP eller ljudtest.

## Fortsatta gränser

Även om ACL säger ja är faktiskt lyckad kernel-open, AppArmor/LSM-beslut, firmware, DSP process domain och QNN-initiering **inte** verifierade. Vid ACL-parsningsfel faller kontrollen tillbaka till unknown, inte ett gissat ja.

**Förbjudna steg i detta spår:** chmod, chown, udev-reload eller ändring, gruppmedlemsändring, sudo, service-omstart, körning av 4B-modell eller tiny HTP-modell, ljudinspelning och sammanslagning till main. PR #110 historisk säkerhetsrensning är alltjämt separat releaseblockerare.

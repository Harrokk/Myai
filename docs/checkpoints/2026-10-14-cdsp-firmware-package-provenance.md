# MyAI kontrollpunkt – CDSP firmware och FastRPC-paketproveniens

Datum: 2026-10-14. Utvecklingsgren: dev/ventuno-cdsp-firmware-dpkg-provenance-20261014. Endast DRAFT – ej merge, deployment eller omstart.

## Verifierade utgångsläge

- [PR #165 – skrivskyddad firmwarekontroll #38602174764](https://github.com/Harrokk/Myai/actions/runs/38602174764): på verklig VENTUNO identifierades exakt en CDSP som `running`, och det validerade sysfs firmware-namnet hade en vanlig fil i de fyra dokumenterade sökvägarna. Ingen firmwarefil öppnades. En hittad fil bevisar inte binäridentitet med den laddade firmwarebilden.
- [PR #165 – full isolerad ARM64 CI #38602281150](https://github.com/Harrokk/Myai/actions/runs/38602281150): **1930 passed, 14 skipped**, statisk source/privacy audit PASS med 0 blockerande fynd. En tidigare manuell granskningsflagga för `exec` i en isolerad testfil kvarstår.
- [PR #164](https://github.com/Harrokk/Myai/pull/164) verifierade Hexagon ELF-format för `fastrpc_shell_unsigned_3`; PR #161 verifierade paketerad Hexagon V75 Skel. PR #163 rättade äldre experimentell Skel-väljare men är fortfarande DRAFT. Faktisk QNN HTP-inferens är fortfarande **inte verifierad**.

## Nytt syfte

Linux remoteproc:s `firmware`-attribut uppges visa firmware-namnet som används, med reservation för autonomt startade enheter och specialfall. Det bevisar inte innehåll, versionsmatchning eller exekverbarhet:
https://sources.debian.org/src/linux/6.12.101-1/Documentation/ABI/testing/sysfs-class-remoteproc
https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux.git/+/refs/tags/v5.10-rc5/drivers/remoteproc/remoteproc_sysfs.c

Vi vill veta om den **redan lokaliserade** CDSP firmwarefilen är paketägd, och hur det relaterar till redan installerad FastRPC-shell, utan att läsa binärinnehåll eller härleda fel från olika paketversioner.

## Den nya strikt begränsade rapporten

- `scripts/ventuno_cdsp_dpkg_provenance_readonly.py` använder samma enda, Device Tree-verifierade `running` CDSP som i tidigare prob; max 192 validerade ASCII-tecken i sysfs firmware-namnet, inga absoluta vägar eller traversal.
- Undersöker bara redan kända Linux `/lib/firmware` kandidatsökvägar med `resolve`/`lstat`, högst fyra sökvägar; inga bilder öppnas eller läses, ingen hashing, inga katalogtraverseringar.
- Anropar `dpkg-query -S` endast på giltiga lokala kandidater och deras lösta vanliga filer, samt på den kända `/usr/lib/dsp/cdsp/fastrpc_shell_unsigned_3` och dess lösta mål inom `/usr`. `dpkg-query -W` sker **endast** om paketnamnet tillhör en explicit allowlist (firmware-qcom-soc, linux-firmware, qcom-firmware, qairt-libs, qairt-dsp-binaries, qcom-fastrpc1).
- Hämtade paketnamn utanför allowlisten omvandlas till `other_dpkg_package`. All versionsutmatning måste uppfylla tidigare testad, begränsad Debian-versionregex. Inga råa dpkg-rader, loggar, firmware-paths, filnamn, användar-ID:n eller externa symlink-mål skrivs ut.
- Hanterar flera firmwarekandidater med olika paketägarskap som `ambiguous_candidates` i stället för att välja godtyckligt. En saknad dpkg-träff kan vara ett vendor-/firmwareoverlay och bevisar **inte** manipulation eller felaktig firmware.
- Tio syntetiska regressionstester, isolerad ARM64 CI och strikt workflow med exakt commit i temporär utcheckning.
- Rapporten lämnar alltid `matching_firmware_build_and_shell_verified=false`, `running_firmware_binary_verified=false` och `signed_or_unsigned_pd_verified=false`. Ingen `/dev`-nod öppnas och inget modelltest utförs.

## Stopplinje

Metadata kan visa paketproveniens och explicit version **inom samma paketfamilj**, men firmware- och QAIRT-paket använder olika versionsscheman. Sätt aldrig likhet mellan deras versionssträngar som krav för HTP-kompatibilitet. Ingen apt-installation, sudo, chmod/chown, udev/ACL/grupp-ändring, serviceomstart, firmwarebildläsning, Geniex/LLM/QNN-anrop, USB-ljud, kamera eller main-merge. GitHub historisk sekretess-/Support purge PR #110 är fortsatt separat releaseblockerare.

Efter verifierad körning: utvärdera **om paketägarskap ger någon konkret avvikelse**. Om allt finns, avsluta metadatakedjan och fokusera framtida analys på DSP process domain / HTP backend konfigurationskontrakt, utan ett nytt blint HTP-försök.

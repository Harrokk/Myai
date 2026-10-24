#!/usr/bin/env bash
# MyAI: supervised, single-use App Lab ASR microphone test guard.
# This script never opens a microphone, launches models, or runs an App itself.
# It pauses ONLY the existing GenieX service while the operator clicks Run once
# in Arduino App Lab; its EXIT trap restores GenieX even after Ctrl+C/HUP/TERM.
set -Eeuo pipefail

MODEL_UNIT=myai-geniex.service
MYAI_UNIT=myai-ventuno.service
restoration_required=0

restore_geniex() {
    local original_status=$?
    trap - EXIT INT TERM HUP
    if (( restoration_required )); then
        printf '\nÅterstartar GenieX efter testfönstret...\n'
        if sudo systemctl start "$MODEL_UNIT" && systemctl is-active --quiet "$MODEL_UNIT"; then
            printf 'GenieX är åter aktiv.\n'
        else
            printf 'VARNING: GenieX kunde inte verifieras aktiv! Kör manuellt: sudo systemctl start %s\n' "$MODEL_UNIT" >&2
            original_status=2
        fi
    fi
    exit "$original_status"
}
trap restore_geniex EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [[ "$(uname -m)" != aarch64 || "$(id -un)" != arduino || ! -t 0 ]]; then
    printf 'Avbryter: kräver interaktiv terminal som användaren arduino på Ventuno Q.\n' >&2
    exit 2
fi
if ! command -v sudo >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
    printf 'Avbryter: sudo eller systemctl saknas.\n' >&2
    exit 2
fi
if ! systemctl is-active --quiet "$MODEL_UNIT" || ! systemctl is-active --quiet "$MYAI_UNIT"; then
    printf 'Avbryter: både MyAI och GenieX måste vara aktiva före testet.\n' >&2
    exit 2
fi
if [[ ! -c /dev/snd/pcmC1D0c ]] || ! grep -Eq '^[[:space:]]*0?1-0?0:.*capture[[:space:]]+[1-9]' /proc/asound/pcm; then
    printf 'Avbryter: USB-mikrofonens gamla ALSA-par 1:0 kunde inte verifieras.\n' >&2
    exit 2
fi

printf 'Förkontroll OK. Importera den verifierade ZIP-appen i Arduino App Lab.\n'
printf 'Tryck INTE på Run ännu. Ingen inspelning har startats.\n'
printf 'Kontrollera att ingen utomstående är inom mikrofonens räckvidd.\n'
printf 'Tryck Enter när App Lab-appen är klar att köras (eller Ctrl+C för att avbryta): '
IFS= read -r _

# Validate sudo *before* changing service state.
sudo -v
printf '\nPauserar endast GenieX; MyAI och GitHub-runnern lämnas orörda...\n'
restoration_required=1
sudo systemctl stop "$MODEL_UNIT"
if systemctl is-active --quiet "$MODEL_UNIT"; then
    printf 'Avbryter: GenieX stannade inte.\n' >&2
    exit 2
fi
if ! systemctl is-active --quiet "$MYAI_UNIT"; then
    printf 'Avbryter: MyAI slutade vara aktiv.\n' >&2
    exit 2
fi

printf '\nTESTFÖNSTER ÖPPET: Klicka Run EXAKT EN GÅNG i App Lab.\n'
printf 'När du ser MYAI_ASR: capture-begins, säg "Vad heter du?" under femsekundersfönstret.\n'
printf 'Notera bara MYAI_ASR:s resultatkod. Klicka Stop om appen inte avslutas själv.\n'
printf 'Återgå hit och tryck Enter när testet är avslutat.\n'
printf 'Säkerhet: efter högst 10 minuter avslutas testfönstret och GenieX återstartas.\n'
if ! IFS= read -r -t 600 -p 'Tryck Enter för att återställa GenieX: ' _; then
    printf '\nTestfönstret avslutades eller avbröts; återställer GenieX.\n'
fi

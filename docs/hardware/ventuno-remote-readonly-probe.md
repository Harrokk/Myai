# Real VENTUNO remote read-only hardware inventory

This source performs privacy-sanitized hardware observation on the real
VENTUNO Q using its existing registered GitHub Actions runner, not a
simulation. The read-only workflow fetches the exact branch commit into
a disposable runner temporary checkout and executes Python with -B.

Only counters or safe statuses are emitted: CPU clocks, thermal range,
available memory and disk, USB device counts, count of USB class-Audio
interfaces, ALSA cards, input/output PCM nodes, Wi-Fi link state,
Bluetooth HCI count, kernel accelerator device node indicators,
remoteproc state counts, presence of limited Qualcomm QNN/SNPE/RPC
shared libraries in standard system directories, and active service
categories for MyAI, GenieX and its GitHub runner.

No IPs, MAC addresses, network SSIDs, Bluetooth paired device names,
USB serials, users, files, audio samples, camera images or passwords
are printed. No microphone capture, speaker output, network scan,
service restart, sudo, OS modification or production model inference
is attempted.

The presence of an ALSA card does not guarantee USB microphone support.
Missing standard-location QNN libraries or generic /dev/accel nodes do not
prove the board lacks an NPU. Source vendor packages may be in other paths
or expose other interfaces. Active systemd status is not proof of working
MyAI speech or user interaction. Further functional testing requires
explicitly scoped commands and, for ambient audio recording, privacy care.

Do not use the temporary Actions checkout as the live MyAI service.

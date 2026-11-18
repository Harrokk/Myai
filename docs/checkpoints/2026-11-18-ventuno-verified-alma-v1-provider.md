# 2026-11-18 – retain working Alma V1 while completing MyAI

Parent: PR #416. This is a **source-only DRAFT**, not a voice-model
training task or a deployment.

## Real issue confirmed

The pre-existing \`modules/voice/piper_alma_provider.py\` pinned legacy ONNX
SHA-256 \`f75455eb...\` and required a sidecar of at least 4000 bytes carrying
\`dataset=alma\` and \`language.code=sv_SE\`.

The actual operator-tested Arduino App Lab ZIP has:
- \`sv_SE-alma-medium.onnx\`, exactly 63,434,611 bytes, SHA-256
  \`b4bfecd22e30cf28f514eeea06c0da440be1721435a652d0571ee65963ce8f65\`
- \`sv_SE-alma-medium.onnx.json\`, exactly 3,907 bytes, SHA-256
  \`f7467e5d2ada0239004fca552f42b25ac90a92b848e5c283aec13a1f26a85f84\`
- Its sidecar legitimately lacks \`dataset\` and \`language\` but includes
  \`audio.sample_rate=22050\`, \`espeak.voice=sv\`, \`num_speakers=1\`.
These exact files and hashes were already recorded in
\`integrations/arduino_app_lab/alma_reference/source_contract.py\`.

Before this change MyAI's Piper provider would reject the exact known-good
model by hash AND metadata, even though the operator proved it on hardware.

## Change

Keep the original legacy pinned model acceptance unchanged. Add a second
*exact model-and-sidecar SHA-256 pair*, with exact byte sizes, validated
Swedish voice and 22050-Hz audio. If either file differs, refuse.

The VENTUNO profile remains disabled for TTS and voice. Voice provider
selection already exists (\`pyttsx3\` or \`piper_alma\`); this patch does not
introduce a new framework or install any model. The operator's on-device
App Lab voice pipeline, GenieX and MyAI production are unchanged.

## Verification and next gates

- Eight synthetic read-only model/sidecar fixture tests; use a sparse fake
  60 MB file to test actual SHA calculation, no bundled audio/model weights.
- GitHub-hosted ARM64 full test run must succeed for exact PR head.
- Before first physically authorized rollout, independently select an
  explicit audio output device, disable unwanted persistent memory writes
  for App Lab bridge, coordinate ASR/mic/NPU ownership, then verify runtime
  Piper package and ONNX-format compatibility. No physical sound or device
  test performed here.
- Do not confuse accepting files with proving live performance or
  changing the voice's Swedish pronunciation. Alma V2 training is deferred.

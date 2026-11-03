// GitHub-hosted AArch64 smoke probe for exact pinned upstream audio decoders.
// No model weights, microphones, native STT inference or private recordings.
// Outputs only an exit status. See docs/checkpoints/2026-11-03-native-wav-smoke.md.

#include <cstddef>
#include <cstdlib>

#if defined(MYAI_CANARY_WAV)
#include "wav.h"
#include <string>
#include <vector>

int main(int argc, char **argv) {
    if (argc != 2 || argv[1] == nullptr) return 2;
    std::vector<float> pcm;
    std::string error;
    if (!transcribe_cli::load_wav_mono_16k(argv[1], pcm, error)) return 3;
    // Must read all eight synthetic mono 16k samples from the sealed memfd.
    return pcm.size() == 8 ? 0 : 4;
}
#elif defined(MYAI_WHISPER_MINIAUDIO)
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"

int main(int argc, char **argv) {
    if (argc != 2 || argv[1] == nullptr) return 2;
    const ma_decoder_config cfg =
        ma_decoder_config_init(ma_format_f32, 1, 16000);
    ma_decoder decoder;
    if (ma_decoder_init_file(argv[1], &cfg, &decoder) != MA_SUCCESS) return 3;
    float pcm[8] = {};
    ma_uint64 read_count = 0;
    const ma_result status =
        ma_decoder_read_pcm_frames(&decoder, pcm, 8, &read_count);
    ma_decoder_uninit(&decoder);
    return (status == MA_SUCCESS && read_count == 8) ? 0 : 4;
}
#else
#error "Select exactly one pinned native decoder implementation"
#endif

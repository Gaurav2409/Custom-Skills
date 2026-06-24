# Dialogue Extractor

A professional VST3 plugin that isolates clean dialogue and voiceover from mixed audio — removing music beds, SFX, backing vocals, and ambient noise using a four-stage AI separation pipeline.

---

## What It Does

Dialogue Extractor runs audio through four successive AI models, each stripping a different layer of unwanted content:

| Pass | Model | Removes |
| ---- | ----- | ------- |
| 1 | UVR-MDX-NET-Inst_HQ_3 | Music beds, instrumentation, SFX |
| 2 | UVR-MDX-NET-KARA_2 | Backing vocals, choir, harmony |
| 3 | MelBand RoFormer | Residual bleed (state-of-the-art SDR 12.6 dB) |
| 4 | DeepFilterNet3 | Broadband noise, reverb tail |

The output is a spectrally clean dialogue/voiceover track normalised to −14 LUFS (EBU R128 streaming standard), exported as 24-bit stereo WAV.

---

## Installation

Copy `Dialogue Extractor.vst3` to `~/Library/Audio/Plug-Ins/VST3/`, then rescan plugins in your DAW (Reaper, Ableton Live, Cubase, Studio One, Bitwig).

---

## How to Use

1. Insert **Dialogue Extractor** as an effect on any audio track in your DAW
2. Press **● CAPTURE** — the plugin records audio passing through it in real time
3. Play the region you want to process; press **■ STOP** when done
4. Press **▶ PROCESS** — the four-stage pipeline runs in the background with per-pass progress
5. When complete, the plugin switches to Playback mode — processed audio plays back through the plugin output
6. Press **EXPORT WAV** to save the clean dialogue as a 24-bit WAV file

---

## UI

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ◆ DIALOGUE EXTRACTOR                          SOUNDSCAPER AI   v1.0.0  │
│──────────────────────────────────────────────────────────────────────────│
│  INPUT ────────────────────────────────────────────────────────────────  │
│  [ Orange waveform — captured input audio ]                               │
│  OUTPUT ───────────────────────────────────────────────────────────────  │
│  [ Cyan waveform — processed output audio ]                               │
│                                                                           │
│  SEPARATION CHAIN ─────────────────────────────────────────────────────  │
│  ┌─────────────────────────┐  ┌─────────────────────────┐                │
│  │ ● PASS 1       [ON/OFF] │  │ ● PASS 2       [ON/OFF] │                │
│  │ MDX-Net Instrumental    │  │ MDX-Net KARA            │                │
│  └─────────────────────────┘  └─────────────────────────┘                │
│  ┌─────────────────────────┐  ┌─────────────────────────┐                │
│  │ ● PASS 3       [ON/OFF] │  │ ● PASS 4       [ON/OFF] │                │
│  │ MelBand RoFormer        │  │ DeepFilterNet3          │                │
│  └─────────────────────────┘  └─────────────────────────┘                │
│──────────────────────────────────────────────────────────────────────────│
│  [ ● CAPTURE ]  [ ━━━━━━━━━━━━━━━━ Pass 3/4 · 23s left ]  [ EXPORT ]  │
│  IN ████████░ −12.3 dBFS          OUT ████████████ −14.0 LUFS            │
└──────────────────────────────────────────────────────────────────────────┘
```

Each pass card shows real-time state (Waiting → Processing → Done ✓). Passes can be toggled individually for A/B comparison or faster processing.

---

## Requirements

- macOS 12+ (Monterey or later), Apple Silicon (arm64)
- ONNX Runtime: `brew install onnxruntime`
- Python 3.11 + `audio-separator` (Pass 3): `pip install audio-separator`
- Python 3.11 + DeepFilterNet (Pass 4): `pip install deepfilternet`

---

## Output Specification

| Property | Value |
|----------|-------|
| Sample rate | 44.1 kHz |
| Bit depth | 24-bit PCM WAV |
| Channels | Stereo |
| Integrated loudness | −14 LUFS (EBU R128) |
| True peak | −1 dBTP |

---

*Dialogue Extractor — Soundscaper AI v1.0.0*

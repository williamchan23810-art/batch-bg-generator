# Batch Background & Effects Generator (`batch-bg-generator`)

Autonomous multi-scene image sequence and video background generator for music and karaoke video production.

## Architecture & Directory Structure

```text
batch-bg-generator/
├── .gitignore
├── README.md
├── requirements.txt
├── config.example.json
├── batch_bg_engine.py
└── output/
```

## Key Features

- **Pacing Calculation**: Divides `total_duration` across `total_frames` (`base_duration = total_duration / total_frames`) with $\pm 8\%$ micro-variations normalized to match the exact target duration.
- **Composition Guardrail**: Enforces a lower-third negative space constraint in every prompt and synthesized frame (darker, low-contrast, empty lower 30% for 2-row karaoke subtitle legibility).
- **Randomized Motion & Transition Matrix**:
  - Camera movements per clip: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `drift_up`.
  - Smooth scene cross-fades via FFmpeg's `xfade` filter (`fade`, `dissolve`, `wipeleft`, `wiperight`, `smoothleft`).
- **Broad Player Compatibility**: Renders H.264 (`libx264`) video in an `.mp4` container with `yuv420p` pixel format and no audio stream (`-an`).

## Usage

### 1. Run with CLI Arguments
```bash
# 16:9 Landscape (1920x1080)
python batch_bg_engine.py --aspect-ratio 16:9 --duration 30 --frames 5 --output output/bg_16x9.mp4

# 9:16 Portrait for Shorts / Reels (1080x1920)
python batch_bg_engine.py --aspect-ratio 9:16 --duration 30 --frames 5 --output output/bg_9x16.mp4
```

### 2. Run with JSON Configuration File
```bash
python batch_bg_engine.py --config config.example.json
```

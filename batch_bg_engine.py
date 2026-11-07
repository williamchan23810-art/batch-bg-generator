import os
import sys
import json
import math
import random
import shutil
import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

NARRATIVE_ARC_STAGES = [
    ("Establishing Atmosphere", "distant horizon and quiet opening mood, gentle mist"),
    ("Awakening Detail", "emerging streetlamp glow and shimmering surface reflections"),
    ("Rising Emotion", "deepening color contrast, expressive brushwork and dramatic shadows"),
    ("Midpoint Resonance", "vibrant golden and neon highlights cutting through the night"),
    ("Intimate Reflection", "softly diffused bokeh lights and rain-slicked textures"),
    ("Climactic Crescendo", "radiant atmospheric bloom, rich impasto light trails"),
    ("Lingering Echoes", "cooling twilight tones with warm amber embers fading"),
    ("Final Resolution", "serene nocturnal stillness and deep velvety negative space"),
]


def resolve_ffmpeg_binary() -> str:
    """Locate ffmpeg binary from workspace ffmpeg-static or system PATH."""
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "node_modules" / "ffmpeg-static" / "ffmpeg.exe",
        script_dir / "node_modules" / "ffmpeg-static" / "ffmpeg",
        script_dir.parent / "karaoke-creation-engine" / "node_modules" / "ffmpeg-static" / "ffmpeg.exe",
        script_dir.parent / "karaoke-creation-engine" / "node_modules" / "ffmpeg-static" / "ffmpeg",
        script_dir.parent / "node_modules" / "ffmpeg-static" / "ffmpeg.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError("FFmpeg binary not found in node_modules/ffmpeg-static or PATH.")


def synthesize_storyboard_frame(
    scene_index: int,
    total_frames: int,
    width: int,
    height: int,
    song_theme: str,
    style_anchor: str,
    output_path: str,
):
    """
    Autonomously synthesize a high-resolution cinematic artwork frame when no external
    ComfyUI / Imagen endpoint is connected, enforcing the bottom-30% negative space rule.
    """
    rng = np.random.default_rng(seed=1000 + scene_index * 37)
    progress = (scene_index - 1) / max(1, total_frames - 1)

    rw, rh = max(270, width // 2), max(480, height // 2)
    y_norm = np.linspace(0.0, 1.0, rh, dtype=np.float32)[:, None]
    x_norm = np.linspace(0.0, 1.0, rw, dtype=np.float32)[None, :]

    palettes = [
        ((14, 24, 46), (38, 68, 110), (235, 145, 55)),
        ((18, 22, 48), (62, 54, 115), (255, 115, 85)),
        ((12, 28, 44), (28, 88, 118), (250, 180, 65)),
        ((24, 20, 42), (92, 48, 98), (56, 195, 245)),
    ]
    sky_rgb, mid_rgb, accent_rgb = palettes[(scene_index - 1) % len(palettes)]

    img_arr = np.zeros((rh, rw, 3), dtype=np.float32)
    for c in range(3):
        upper_blend = sky_rgb[c] * (1.0 - y_norm) + mid_rgb[c] * y_norm
        img_arr[:, :, c] = upper_blend

    focal_x = 0.28 + 0.44 * ((math.sin(scene_index * 1.35) + 1.0) * 0.5)
    focal_y = 0.34 + 0.10 * math.cos(scene_index * 0.9)
    dist_sq = ((x_norm - focal_x) * 1.15) ** 2 + ((y_norm - focal_y) * 1.45) ** 2
    glow = np.exp(-dist_sq / (0.08 + 0.04 * progress))
    for c in range(3):
        img_arr[:, :, c] += glow * accent_rgb[c] * 0.78

    refl_mask = np.exp(-((y_norm - 0.56) ** 2) / 0.018) * np.exp(-((x_norm - focal_x) ** 2) / 0.06)
    ripples = 0.5 + 0.5 * np.sin(y_norm * 140.0 + x_norm * 25.0 + scene_index * 2.0)
    for c in range(3):
        img_arr[:, :, c] += refl_mask * ripples * accent_rgb[c] * 0.55

    brush_noise = rng.normal(0.0, 6.5, size=(rh // 2, rw // 2, 3)).astype(np.float32)
    brush_img = Image.fromarray(np.clip(brush_noise + 128, 0, 255).astype(np.uint8)).resize(
        (rw, rh), resample=Image.Resampling.BILINEAR
    )
    img_arr += (np.asarray(brush_img, dtype=np.float32) - 128.0) * 0.35

    base_pil = Image.fromarray(np.clip(img_arr, 0, 255).astype(np.uint8)).resize(
        (width, height), resample=Image.Resampling.BICUBIC
    )
    draw = ImageDraw.Draw(base_pil, "RGBA")

    for _ in range(28):
        bx = int(rng.uniform(0.06, 0.94) * width)
        by = int(rng.uniform(0.08, 0.66) * height)
        rad = int(rng.uniform(14, 68) * (width / 1080.0))
        col_choice = accent_rgb if rng.random() < 0.65 else (120, 200, 255)
        alpha = int(rng.uniform(22, 68))
        draw.ellipse(
            [bx - rad, by - rad, bx + rad, by + rad],
            fill=(col_choice[0], col_choice[1], col_choice[2], alpha),
        )

    if "rain" in song_theme.lower() or "lounge" in song_theme.lower():
        for _ in range(65):
            rx = int(rng.uniform(0, width))
            ry = int(rng.uniform(0, int(height * 0.72)))
            rlen = int(rng.uniform(25, 75))
            draw.line(
                [(rx, ry), (rx - 6, ry + rlen)],
                fill=(210, 228, 255, int(rng.uniform(24, 58))),
                width=2,
            )

    base_pil = base_pil.filter(ImageFilter.GaussianBlur(radius=1.8))

    # Composition Guardrail: Keep lower 30% dark, low-contrast negative space for 2-row subtitles
    final_arr = np.asarray(base_pil, dtype=np.float32)
    fy = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    fx = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]

    bottom_scrim = np.clip((fy - 0.58) / 0.42, 0.0, 1.0) ** 1.35
    dark_target = np.array([8.0, 10.0, 15.0], dtype=np.float32)[None, None, :]
    final_arr = final_arr * (1.0 - 0.88 * bottom_scrim) + dark_target * (0.88 * bottom_scrim)

    rad_dist = ((fx - 0.5) * 1.3) ** 2 + ((fy - 0.42) * 1.1) ** 2
    vignette = np.clip(1.0 - 0.45 * rad_dist, 0.45, 1.0)
    final_arr *= vignette

    out_pil = Image.fromarray(np.clip(final_arr, 0, 255).astype(np.uint8))
    out_pil.save(output_path, format="PNG")


def generate_batch_background(
    song_theme: str,
    total_duration: float,
    total_frames: int,
    aspect_ratio: str = "16:9",
    style_anchor: str = None,
    style_override: str = None,
    output_filename: str = "output/background_track.mp4",
):
    # 1. Resolution & Dimension Setup
    is_portrait = (aspect_ratio == "9:16")
    width, height = (1080, 1920) if is_portrait else (1920, 1080)

    effective_style = style_override or style_anchor
    if not effective_style:
        effective_style = (
            f"cinematic fine art illustration representing '{song_theme}', "
            "harmonious color grading, expressive lighting, professional concept art, "
            "masterpiece quality, uncluttered bottom third"
        )

    # Composition Guardrail: Negative space enforcement for 2-row subtitles
    framing_rule = (
        f"{aspect_ratio} aspect ratio, subject positioned in upper center, "
        "dark low-contrast empty background in lower 30 percent, clean composition, no text"
    )

    # 3. Pacing Calculation: base_duration = total_duration / total_frames with +/- 8% micro-variations
    total_frames = max(1, int(total_frames))
    total_duration = float(total_duration)
    base_duration = total_duration / total_frames
    print(f"🎬 Generating {total_frames} frames for {total_duration}s runtime ({aspect_ratio} @ {width}x{height})")
    print(f"⏱️ Average duration per scene: {base_duration:.2f}s")

    # Randomized Motion & Transition Matrix
    motion_effects = [
        "zoom_in",
        "zoom_out",
        "pan_left",
        "pan_right",
        "drift_up",
    ]

    transitions = [
        "fade",
        "dissolve",
        "wipeleft",
        "wiperight",
        "smoothleft",
    ]

    os.makedirs("temp_frames", exist_ok=True)
    out_dir = os.path.dirname(output_filename)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Micro-variation in scene hold timing (+/- 8% around base_duration, normalized to total_duration)
    raw_durations = [base_duration * random.uniform(0.92, 1.08) for _ in range(total_frames)]
    scale_factor = total_duration / sum(raw_durations)
    durations = [round(d * scale_factor, 2) for d in raw_durations]
    durations[-1] = round(total_duration - sum(durations[:-1]), 2)

    frame_manifest = []

    # 4. Generate Frame Prompts & Random Assignments
    for i in range(total_frames):
        scene_index = i + 1
        motion = random.choice(motion_effects)
        trans = random.choice(transitions)
        duration = durations[i]

        arc_title, arc_desc = NARRATIVE_ARC_STAGES[i % len(NARRATIVE_ARC_STAGES)]
        img_filename = f"temp_frames/frame_{scene_index:03d}.png"
        prompt = (
            f"Scene {scene_index} of {total_frames} ({arc_title} - {arc_desc}): "
            f"{song_theme}, narrative progression stage {scene_index}, "
            f"{effective_style}, {framing_rule}"
        )

        synthesize_storyboard_frame(
            scene_index=scene_index,
            total_frames=total_frames,
            width=width,
            height=height,
            song_theme=song_theme,
            style_anchor=effective_style,
            output_path=img_filename,
        )

        frame_manifest.append({
            "scene_index": scene_index,
            "narrative_stage": arc_title,
            "prompt": prompt,
            "file": img_filename,
            "duration": duration,
            "motion": motion,
            "transition": trans,
        })
        print(f"  🖼️ Scene {scene_index:02d}/{total_frames:02d} | {duration:5.2f}s | motion={motion:<10} | xfade={trans:<10} | {arc_title}")

    manifest_json_path = "temp_frames/storyboard_manifest.json"
    with open(manifest_json_path, "w", encoding="utf-8") as mf:
        json.dump(
            {
                "song_theme": song_theme,
                "total_duration": total_duration,
                "total_frames": total_frames,
                "aspect_ratio": aspect_ratio,
                "resolution": f"{width}x{height}",
                "style_override": effective_style,
                "frames": frame_manifest,
            },
            mf,
            indent=2,
        )

    # 5. Build Dynamic FFmpeg Assembly with Camera Motions + Smooth xfade Filter Between Scene Boundaries
    ffmpeg_bin = resolve_ffmpeg_binary()
    fps = 30
    xfade_dur = 0.8 if total_frames > 1 else 0.0
    clip_files = []
    clip_actual_durations = []

    pre_w = int(round((width * 1.2) / 2) * 2)
    pre_h = int(round((height * 1.2) / 2) * 2)

    for i, item in enumerate(frame_manifest):
        clip_path = f"temp_frames/clip_{i + 1:03d}.mp4"
        # Add xfade_dur to non-final clips so after (N-1) xfade overlaps, total duration equals total_duration
        clip_dur = float(item["duration"]) + (xfade_dur if i < total_frames - 1 else 0.0)
        clip_dur = max(1.5, round(clip_dur, 2))
        frames_count = max(1, int(round(clip_dur * fps)))
        motion = item["motion"]

        if motion in ("zoom_out", "slow_zoom_out"):
            z_expr = f"1.15-0.15*(on/{frames_count})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion in ("pan_left", "pan_right_to_left"):
            z_expr = "1.12"
            x_expr = f"(iw-iw/zoom)*(1-on/{frames_count})"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion in ("pan_right", "pan_left_to_right"):
            z_expr = "1.12"
            x_expr = f"(iw-iw/zoom)*(on/{frames_count})"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion in ("drift_up", "subtle_drift_up"):
            z_expr = f"1.08+0.05*(on/{frames_count})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"(ih-ih/zoom)*(1-on/{frames_count})"
        else:  # zoom_in / slow_zoom_in
            z_expr = f"1.0+0.15*(on/{frames_count})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"

        vf_chain = (
            f"scale={pre_w}:{pre_h},"
            f"zoompan=z='{z_expr}':d={frames_count}:x='{x_expr}':y='{y_expr}':s={width}x{height}:fps={fps},"
            f"format=yuv420p"
        )

        clip_cmd = [
            ffmpeg_bin, "-y",
            "-i", item["file"],
            "-vf", vf_chain,
            "-t", f"{clip_dur:.2f}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            "-r", str(fps),
            "-pix_fmt", "yuv420p",
            "-an",
            clip_path,
        ]
        subprocess.run(clip_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        clip_files.append(clip_path)
        clip_actual_durations.append(clip_dur)

    # Assemble clips using FFmpeg's xfade filter across scene boundaries
    if len(clip_files) == 1:
        shutil.copyfile(clip_files[0], output_filename)
    else:
        inputs_args = []
        for clip in clip_files:
            inputs_args.extend(["-i", clip])

        filter_parts = []
        accumulated_offset = clip_actual_durations[0] - xfade_dur
        prev_label = "0:v"

        for idx in range(1, len(clip_files)):
            next_label = f"{idx}:v"
            out_label = f"v{idx}" if idx < len(clip_files) - 1 else "vout"
            trans_name = frame_manifest[idx - 1]["transition"]
            offset_val = max(0.1, round(accumulated_offset, 2))
            filter_parts.append(
                f"[{prev_label}][{next_label}]xfade=transition={trans_name}:duration={xfade_dur:.2f}:offset={offset_val:.2f}[{out_label}]"
            )
            prev_label = out_label
            if idx < len(clip_files) - 1:
                accumulated_offset += clip_actual_durations[idx] - xfade_dur

        filter_complex = ";".join(filter_parts)
        cmd = [
            ffmpeg_bin, "-y",
            *inputs_args,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-r", str(fps),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-an",
            output_filename,
        ]
        print("🚀 Rendering background MP4 via FFmpeg (xfade transitions, H.264, yuv420p, no audio)...")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    print(f"✅ Finished: {output_filename} ({os.path.getsize(output_filename) / (1024 * 1024):.2f} MB)")
    return {
        "output_filename": os.path.abspath(output_filename),
        "manifest_path": os.path.abspath(manifest_json_path),
        "frames": frame_manifest,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Batch Background & Effects Generator")
    parser.add_argument("--config", type=str, help="Path to input JSON configuration file")
    parser.add_argument("--json", type=str, help="Inline JSON configuration string")
    parser.add_argument(
        "--song-theme",
        type=str,
        default="Late-night rain in 1950s urban lounge, neon reflections on wet cobblestones, soulful melancholy",
        help="Subject, emotion, and musical vibe",
    )
    parser.add_argument("--duration", type=float, default=60.0, help="Total runtime in seconds")
    parser.add_argument("--frames", type=int, default=8, help="Total number of distinct images to generate")
    parser.add_argument("--aspect-ratio", type=str, default="9:16", choices=["16:9", "9:16"], help="16:9 or 9:16")
    parser.add_argument("--style-override", type=str, default=None, help="Optional specific art medium")
    parser.add_argument("--output", type=str, default=None, help="Output MP4 filename")
    args = parser.parse_args()

    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as cf:
            cfg = json.load(cf)
        generate_batch_background(
            song_theme=cfg.get("song_theme", args.song_theme),
            total_duration=float(cfg.get("total_duration", args.duration)),
            total_frames=int(cfg.get("total_frames", args.frames)),
            aspect_ratio=cfg.get("aspect_ratio", args.aspect_ratio),
            style_override=cfg.get("style_override") or cfg.get("style_anchor"),
            output_filename=cfg.get("output_filename", args.output or "output/background_track.mp4"),
        )
    elif args.json:
        cfg = json.loads(args.json)
        generate_batch_background(
            song_theme=cfg.get("song_theme", args.song_theme),
            total_duration=float(cfg.get("total_duration", args.duration)),
            total_frames=int(cfg.get("total_frames", args.frames)),
            aspect_ratio=cfg.get("aspect_ratio", args.aspect_ratio),
            style_override=cfg.get("style_override") or cfg.get("style_anchor"),
            output_filename=cfg.get("output_filename", args.output or "output/background_track.mp4"),
        )
    else:
        default_out = args.output or (
            "output/shorts_background_9x16.mp4"
            if args.aspect_ratio == "9:16"
            else "output/background_track_16x9.mp4"
        )
        generate_batch_background(
            song_theme=args.song_theme,
            total_duration=args.duration,
            total_frames=args.frames,
            aspect_ratio=args.aspect_ratio,
            style_override=args.style_override or "Vintage oil impasto with cinematic moody street lighting",
            output_filename=default_out,
        )

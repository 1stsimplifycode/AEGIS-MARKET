"""Generate the licence-clear media corpus the multimodal pipelines run on.

Three categories, and the distinction is the whole point (spec section 52):

**A. AEGIS-original visuals.** Charts and an animated chart video rendered here from the
real NSE panel. Original work, redistributable, safe for a paper package.

**B. Synthetic test signals.** Audio with analytically known properties (a 220 Hz tone, a
noise burst, an amplitude-modulated envelope). These exist to *verify the extractors* --
a pitch estimator that cannot recover 220 Hz from a 220 Hz tone cannot be trusted on a
real recording. They are labelled SYNTHETIC and are never presented as evidence about any
company.

**C. Third-party references.** Nothing is downloaded. A reference artifact records URL,
publisher and licence verdict only.

    python scripts/make_media.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from research.core import paths
from research.core.licensing import LicenseStatus, MediaLicenseChecker
from research.video.pipeline import reference_artifact
from research.visualization import style

SR = 16000
ORIGINAL_EVIDENCE = ("rendered by AEGIS-Market from the open NSE bhavcopy panel; "
                     "original work of this repository")


def render_charts(panel: pd.DataFrame, symbols: list[str], out: Path) -> list[dict]:
    """Category A: real price/volume charts. These are genuine financial chart images."""
    import matplotlib.pyplot as plt
    style.apply()
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for sym in symbols:
        s = panel[panel["symbol"] == sym].sort_values("date").tail(250)
        if len(s) < 60:
            continue
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(style.ONE_HALF_COL, 3.2), sharex=True,
            gridspec_kw={"height_ratios": [3, 1]})
        ax1.plot(s["date"], s["close"], color=style.PALETTE[0], lw=1.1)
        ax1.fill_between(s["date"], s["low"], s["high"], color=style.PALETTE[0],
                         alpha=0.15, lw=0)
        ax1.set_ylabel("Close (INR)")
        ax1.set_title("%s - last %d sessions to %s"
                      % (sym, len(s), s["date"].max().date()))
        ax2.bar(s["date"], s["volume"], color=style.PALETTE[1], width=1.0, lw=0)
        ax2.set_ylabel("Volume")
        ax2.set_xlabel("Session")
        fig.autofmt_xdate()
        p = out / ("chart_%s.png" % sym.lower())
        fig.savefig(p, dpi=200)
        plt.close(fig)
        made.append({"path": str(p), "symbol": sym, "category": "A_AEGIS_ORIGINAL",
                     "licence": LicenseStatus.AUTHORIZED.value,
                     "evidence": ORIGINAL_EVIDENCE,
                     "sessions": int(len(s)),
                     "window": [str(s["date"].min().date()),
                                str(s["date"].max().date())]})
        print("  chart  %s" % p.name)
    return made


def synth_audio(out: Path) -> list[dict]:
    """Category B: signals whose ground truth is known by construction."""
    import soundfile as sf
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260818)
    made = []

    def emit(name: str, x: np.ndarray, truth: dict) -> None:
        p = out / name
        sf.write(p, np.clip(x, -1, 1).astype(np.float32), SR)
        made.append({"path": str(p), "category": "B_SYNTHETIC_TEST",
                     "licence": LicenseStatus.AUTHORIZED.value,
                     "evidence": "synthesised by scripts/make_media.py; not evidence "
                                 "about any real entity",
                     "ground_truth": truth})
        print("  audio  %s" % name)

    t = np.arange(int(3.0 * SR)) / SR
    emit("tone_220hz.wav", 0.6 * np.sin(2 * np.pi * 220.0 * t),
         {"fundamental_hz": 220.0, "kind": "pure_tone"})

    # Harmonic-rich tone: closer to voiced speech, still exactly known.
    v = sum(0.6 / k * np.sin(2 * np.pi * 140.0 * k * t) for k in (1, 2, 3, 4))
    emit("voiced_140hz.wav", 0.5 * v / np.abs(v).max(),
         {"fundamental_hz": 140.0, "kind": "harmonic_stack"})

    emit("noise_burst.wav", 0.3 * rng.standard_normal(len(t)),
         {"fundamental_hz": None, "kind": "white_noise"})

    # Speech-like: voiced segments separated by silence, so pause_fraction is known.
    seg = np.zeros(int(6.0 * SR))
    ts = np.arange(len(seg)) / SR
    pause_target = 0.4
    on = np.zeros(len(seg), dtype=bool)
    for start in np.arange(0.0, 6.0, 1.0):
        a, b = int(start * SR), int((start + (1 - pause_target)) * SR)
        on[a:b] = True
    carrier = sum(0.5 / k * np.sin(2 * np.pi * 180.0 * k * ts) for k in (1, 2, 3))
    seg = np.where(on, carrier * (0.5 + 0.3 * np.sin(2 * np.pi * 4.0 * ts)), 0.0)
    emit("speechlike_180hz.wav", 0.6 * seg / np.abs(seg).max(),
         {"fundamental_hz": 180.0, "kind": "gated_harmonic",
          "silence_fraction_by_construction": pause_target})
    return made


def render_video(panel: pd.DataFrame, symbol: str, out: Path) -> dict | None:
    """Category A: an original animated chart with a synthetic audio bed.

    The visual content is real market data; the audio bed is a synthetic tone that rises
    with realised volatility, present so the video pipeline's audio branch is genuinely
    exercised. Both facts are recorded in the manifest.
    """
    import subprocess
    import tempfile

    import imageio_ffmpeg
    import matplotlib.pyplot as plt
    import soundfile as sf

    style.apply()
    out.mkdir(parents=True, exist_ok=True)
    s = panel[panel["symbol"] == symbol].sort_values("date").tail(180)
    if len(s) < 60:
        return None

    fps = 10
    n_frames = 60
    idx = np.linspace(30, len(s), n_frames).astype(int)
    tmp = Path(tempfile.mkdtemp(prefix="aegis_vid_"))
    frame_paths = []
    for k, upto in enumerate(idx):
        w = s.iloc[:upto]
        fig, ax = plt.subplots(figsize=(4.8, 2.7), dpi=100)
        ax.plot(w["date"], w["close"], color=style.PALETTE[0], lw=1.4)
        ax.set_xlim(s["date"].min(), s["date"].max())
        ax.set_ylim(s["close"].min() * 0.97, s["close"].max() * 1.03)
        ax.set_title("%s  (AEGIS-Market original render)" % symbol)
        ax.set_ylabel("Close (INR)")
        fig.autofmt_xdate()
        fp = tmp / ("f%03d.png" % k)
        fig.savefig(fp)
        plt.close(fig)
        frame_paths.append(fp)

    ret = np.log(s["close"]).diff()
    vol = ret.rolling(21).std().to_numpy()
    vol = np.nan_to_num(vol[idx - 1], nan=float(np.nanmedian(vol)))
    vol_n = (vol - np.nanmin(vol)) / max(1e-12, np.nanmax(vol) - np.nanmin(vol))
    dur = n_frames / fps
    t = np.arange(int(dur * SR)) / SR
    f0 = 160.0 + 120.0 * np.interp(t, np.linspace(0, dur, len(vol_n)), vol_n)
    bed = 0.35 * np.sin(2 * np.pi * np.cumsum(f0) / SR)
    wav = tmp / "bed.wav"
    sf.write(wav, bed.astype(np.float32), SR)

    mp4 = out / ("chart_%s.mp4" % symbol.lower())
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, "-v", "error", "-y", "-framerate", str(fps),
           "-i", str(tmp / "f%03d.png"), "-i", str(wav),
           # savefig(bbox_inches="tight") yields odd pixel dimensions; libx264 with
           # yuv420p requires both to be even, so crop to the nearest even size.
           "-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
           str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print("  VIDEO FAILED: %s" % r.stderr.strip()[:400])
        return None
    print("  video  %s (%.1f MB)" % (mp4.name, mp4.stat().st_size / 1e6))
    return {"path": str(mp4), "symbol": symbol, "category": "A_AEGIS_ORIGINAL",
            "licence": LicenseStatus.AUTHORIZED.value,
            "evidence": ORIGINAL_EVIDENCE + "; audio bed is a synthetic tone whose "
                        "frequency tracks realised volatility",
            "fps": fps, "frames": n_frames, "duration_s": dur}


def main() -> int:
    paths.ensure_dirs()
    panel = pd.read_parquet(paths.PANEL / "cash_panel.parquet")
    uni = pd.read_parquet(paths.PANEL / "universe.parquet")
    latest = uni[uni["rebalance_date"] == uni["rebalance_date"].max()]
    symbols = latest.sort_values("rank")["symbol"].head(3).tolist()
    print("media symbols: %s" % symbols)

    manifest: dict = {"generated_at": datetime.now(UTC).isoformat(),
                      "categories": {}}
    print("\n[A] charts")
    manifest["categories"]["A_charts"] = render_charts(panel, symbols,
                                                       paths.MEDIA / "images")
    print("\n[B] synthetic audio")
    manifest["categories"]["B_audio"] = synth_audio(paths.MEDIA / "audio")
    print("\n[A] video")
    v = render_video(panel, symbols[0], paths.MEDIA / "video")
    manifest["categories"]["A_video"] = [v] if v else []

    print("\n[C] third-party references (metadata only, nothing downloaded)")
    checker = MediaLicenseChecker()
    refs = []
    for url, title, chan in [
        ("https://www.youtube.com/watch?v=EXAMPLE_ID", "Example market commentary",
         "Example Finance Channel"),
        ("https://www.cnbc.com/video/example", "Example broadcast segment", "CNBC"),
        ("https://www.bloomberg.com/news/videos/example", "Example segment",
         "Bloomberg"),
    ]:
        rec = reference_artifact(url, title=title, channel=chan, checker=checker,
                                 out_dir=paths.MEDIA / "references")
        refs.append(rec)
        print("  ref    %-45s -> %s" % (chan, rec["licence"]["status"]))
    manifest["categories"]["C_references"] = refs

    mp = paths.MANIFESTS / "media_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print("\nmanifest: %s" % mp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

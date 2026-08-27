'use client';

/**
 * Analyse a video clip: choose or upload one, run it, read what the model decided and why.
 *
 * A workflow rather than a card. Nothing appears until a person picks a clip and presses
 * Analyse, and what appears is one run of VIDEO_MODEL_V1 against that input — fetched from
 * the backend, never a stored result. The run id in the footer is the one the backend
 * minted for this request.
 *
 * **Why the takes carry their annotation.** Each offered take shows the expression the
 * RAVDESS actor was directed to portray, before the model runs. Showing it only afterwards
 * would let the panel read as though the model were always right; showing it first means a
 * reader can watch it be wrong, which at this accuracy it often is.
 *
 * **The evidence is the frames themselves.** The backend returns the sampled frames it
 * actually classified, each with the attribution computed for it, so "which moment decided
 * this" is a thing to look at rather than a sentence to believe.
 *
 * **The wording is deliberate.** The model classifies a *performance* against the dataset's
 * annotation. It does not read anyone's inner state, and no copy here says it does.
 *
 * This is inference over a submitted clip. It is not a live or streaming capability.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface Sample {
  id: string;
  actor: string;
  annotated_as: string;
  intensity: string;
  spoken_text: string;
}

interface Offer {
  status: string;
  model_id: string;
  model_available: boolean;
  task: string;
  classes: string[];
  note: string;
  upload: { accepted: string[]; max_bytes: number; how: string };
  source: {
    dataset: string;
    licence: string;
    split: string;
    split_strategy: string;
    actors: string[];
    why_these: string;
  };
  samples: Sample[];
  error?: { reason: string; remedy: string };
}

interface Frame {
  index: number;
  source_frame: number;
  at_s: number;
  relevance: number;
  thumbnail: string;
}

interface Run {
  status: string;
  run_id: string;
  model_id: string;
  model_version: number | null;
  checkpoint: string;
  checkpoint_sha256: string;
  predicted: string;
  confidence: number;
  uncertainty: number;
  posterior: { class: string; probability: number }[];
  parameters: { total: number; trainable: number; frozen: number; pretrained: boolean };
  task: string;
  agreement_with_annotation?: boolean;
  input: Record<string, string | number | null | undefined>;
  provenance: Record<string, string>;
  mode: string;
  note: string;
  evidence?: {
    run_id: string;
    model_id: string;
    explains: string;
    method: string;
    method_note: string;
    timeline: Frame[];
    top_frames: { index: number; at_s: number; relevance: number }[];
    regions: { row: number; col: number; relevance: number }[];
    region_note: string;
    frames_sampled: number;
  };
  error?: { reason: string; remedy: string };
}

export interface VideoMetrics {
  accuracy: number;
  macro_f1: number;
  weighted_f1: number;
  baseline_accuracy: number;
  baseline_macro_f1: number;
  ece: number;
  brier: number;
  samples: number;
  actors: number;
  temporal: string;
  limitation: string;
  robustness: { corruption: string; accuracy: number; macro_f1: number }[];
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function VideoWorkspace({ metrics }: { metrics: VideoMetrics | null }) {
  const [offer, setOffer] = useState<Offer | null>(null);
  const [chosen, setChosen] = useState<string>('');
  const [upload, setUpload] = useState<File | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [why, setWhy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ reason: string; remedy?: string } | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/api/aegis/multimodal/video/samples', {
          cache: 'no-store',
        });
        const payload = (await response.json()) as Offer;
        if (cancelled) return;
        if (payload.status !== 'OK') {
          setFailure({
            reason: payload.error?.reason ?? 'the take list could not be read',
            remedy: payload.error?.remedy,
          });
          return;
        }
        setOffer(payload);
        setChosen(payload.samples[0]?.id ?? '');
      } catch {
        if (!cancelled) {
          setFailure({ reason: 'the backend is not answering' });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const analyse = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    setWhy(false);
    setRun(null);
    try {
      let response: Response;
      if (upload) {
        const form = new FormData();
        form.append('file', upload, upload.name);
        response = await fetch('/api/aegis/multimodal/analyze', {
          method: 'POST',
          body: form,
        });
      } else {
        response = await fetch('/api/aegis/multimodal/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ modality: 'video', clip: chosen }),
        });
      }
      const payload = (await response.json()) as Run;
      if (payload.status !== 'OK') {
        setFailure({
          reason: payload.error?.reason ?? 'the analysis was refused',
          remedy: payload.error?.remedy,
        });
        return;
      }
      setRun(payload);
    } catch {
      setFailure({
        reason: 'the backend is not answering',
        remedy: 'Start it with run_dev.bat and try again.',
      });
    } finally {
      setBusy(false);
    }
  }, [chosen, upload]);

  const selected = offer?.samples.find((s) => s.id === chosen) ?? null;
  const peak = run?.evidence
    ? Math.max(...run.evidence.timeline.map((f) => f.relevance), 1e-9)
    : 1;

  return (
    <section className="home__section audioWork videoWork">
      <div className="home__sectionHead">
        <h2>Analyse a video clip</h2>
      </div>

      <p className="home__caveat" style={{ marginTop: 0 }}>
        {offer?.task ??
          'Facial-expression classification according to the dataset annotation.'}{' '}
        The model reports which labelled performance a clip resembles. It does not measure
        anyone&rsquo;s emotional state.
      </p>

      {failure && !run ? (
        <p className="ticket__refusal" role="status">
          {failure.reason}
          {failure.remedy ? <span className="small muted"> {failure.remedy}</span> : null}
        </p>
      ) : null}

      {offer ? (
        <>
          <div className="audioWork__pick">
            <label className="audioWork__field">
              <span className="audioWork__label">Held-out take</span>
              <select
                value={chosen}
                onChange={(e) => {
                  setChosen(e.target.value);
                  setUpload(null);
                  if (fileInput.current) fileInput.current.value = '';
                }}
              >
                {offer.samples.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.actor} · annotated {s.annotated_as} · {s.intensity}
                  </option>
                ))}
              </select>
            </label>

            <label className="audioWork__field">
              <span className="audioWork__label">or your own video</span>
              <input
                ref={fileInput}
                type="file"
                accept={offer.upload.accepted.join(',')}
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  setUpload(file);
                  if (file) setChosen('');
                }}
              />
            </label>

            <button
              type="button"
              className="btn"
              onClick={() => void analyse()}
              disabled={busy || (!chosen && !upload)}
            >
              {busy ? 'Analysing…' : 'Analyse'}
            </button>
          </div>

          <p className="audioWork__context small muted">
            {upload
              ? `Ready to analyse ${upload.name}.`
              : selected
                ? `${selected.actor} saying “${selected.spoken_text}”, annotated ${selected.annotated_as}.`
                : 'Choose a take.'}{' '}
            <span className="modeOnly modeOnly--research modeOnly--inline">
              {offer.source.why_these} Held-out actors: {offer.source.actors.join(', ')}.
            </span>
          </p>

          {busy ? (
            <p className="videoWork__progress small" role="status">
              <span className="videoWork__spinner" aria-hidden="true" />
              Decoding the clip, sampling frames and running the model. The explanation is
              computed from this run, which takes a few seconds.
            </p>
          ) : null}
        </>
      ) : failure ? null : (
        <p className="small muted">Loading the takes on offer…</p>
      )}

      {run ? (
        <div className="audioResult">
          <p className="audioResult__eyebrow">Video analysed</p>

          <div className="audioResult__grid">
            <div>
              <span className="audioWork__label">Model</span>
              <p className="audioResult__value">{run.model_id}</p>
            </div>
            <div>
              <span className="audioWork__label">Result</span>
              <p className="audioResult__value audioResult__value--big">{run.predicted}</p>
            </div>
            <div>
              <span className="audioWork__label">Confidence</span>
              <p className="audioResult__value">{pct(run.confidence)}</p>
            </div>
            <div>
              <span className="audioWork__label">Uncertainty</span>
              <p className="audioResult__value">{run.uncertainty.toFixed(3)}</p>
            </div>
          </div>

          {typeof run.agreement_with_annotation === 'boolean' ? (
            <p
              className="audioResult__agreement"
              data-agrees={run.agreement_with_annotation}
            >
              {run.agreement_with_annotation
                ? `Matches the dataset annotation (${String(run.input.annotated_as)}).`
                : `Does not match the dataset annotation, which is ${String(
                    run.input.annotated_as,
                  )}.`}
            </p>
          ) : null}

          <p className="audioResult__note small muted">{run.note}</p>

          <button
            type="button"
            className="btn btn--ghost btn--tiny"
            onClick={() => setWhy((v) => !v)}
            aria-expanded={why}
          >
            {why ? 'Hide evidence' : 'Why?'}
          </button>

          {why ? (
            <div className="audioEvidence">
              {run.evidence ? (
                <>
                  <p className="small muted">
                    {run.evidence.method}. {run.evidence.method_note}
                  </p>

                  <h4>Which frames decided it</h4>
                  <ol className="frameStrip">
                    {run.evidence.timeline.map((frame) => {
                      const top = run.evidence!.top_frames.some(
                        (t) => t.index === frame.index,
                      );
                      return (
                        <li key={frame.index} data-top={top}>
                          {frame.thumbnail ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={frame.thumbnail}
                              alt={`Sampled frame at ${frame.at_s.toFixed(2)} seconds`}
                              width={56}
                              height={56}
                            />
                          ) : null}
                          <span className="frameStrip__bar" aria-hidden="true">
                            <span
                              style={{ height: `${(frame.relevance / peak) * 100}%` }}
                            />
                          </span>
                          <span className="frameStrip__time">
                            {frame.at_s.toFixed(1)}s
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                  <p className="small muted">
                    Bar height is that frame&rsquo;s share of the attribution towards{' '}
                    {run.evidence.explains}. Highlighted frames are the four that carried
                    most of it.
                  </p>

                  <h4>Full posterior</h4>
                  <ul className="audioEvidence__bars">
                    {run.posterior.map((p) => (
                      <li key={p.class}>
                        <span className="audioEvidence__span">{p.class}</span>
                        <span className="audioEvidence__bar">
                          <span
                            style={{ width: `${Math.min(p.probability * 100, 100)}%` }}
                          />
                        </span>
                        <span className="audioEvidence__num">{pct(p.probability)}</span>
                      </li>
                    ))}
                  </ul>

                  <div className="modeOnly modeOnly--research">
                    <h4>Where in the face</h4>
                    <p className="small muted">{run.evidence.region_note}</p>
                    <div className="regionGrid" role="img" aria-label="Attribution by region of the face">
                      {run.evidence.regions.map((cell) => (
                        <span
                          key={`${cell.row}-${cell.col}`}
                          style={{ opacity: 0.12 + Math.min(cell.relevance * 6, 0.88) }}
                          title={`row ${cell.row + 1}, column ${cell.col + 1}: ${pct(
                            cell.relevance,
                          )}`}
                        />
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="small muted">No attribution was computed for this run.</p>
              )}

              <div className="modeOnly modeOnly--research audioEvidence__research">
                <h4>Model and data</h4>
                <ul className="audioEvidence__facts">
                  <li>
                    <span>checkpoint</span>
                    <b>{run.checkpoint}</b>
                  </li>
                  <li>
                    <span>checkpoint sha256</span>
                    <b>{run.checkpoint_sha256.slice(0, 24)}…</b>
                  </li>
                  <li>
                    <span>selected at epoch</span>
                    <b>{run.model_version ?? 'n/a'}</b>
                  </li>
                  <li>
                    <span>trainable parameters</span>
                    <b>{run.parameters.trainable.toLocaleString()}</b>
                  </li>
                  <li>
                    <span>frozen parameters</span>
                    <b>{run.parameters.frozen}</b>
                  </li>
                  <li>
                    <span>pretrained weights</span>
                    <b>{run.parameters.pretrained ? 'yes' : 'none'}</b>
                  </li>
                  {Object.entries(run.provenance).map(([k, v]) => (
                    <li key={k}>
                      <span>{k.replace(/_/g, ' ')}</span>
                      <b>{v}</b>
                    </li>
                  ))}
                  <li>
                    <span>input</span>
                    <b>
                      {String(run.input.filename ?? run.input.clip ?? 'video')} ·{' '}
                      {String(run.input.duration_s ?? '?')} s ·{' '}
                      {String(run.input.resolution ?? '?')} ·{' '}
                      {String(run.input.frames_sampled ?? '?')} frames sampled of{' '}
                      {String(run.input.frames_in_clip ?? '?')}
                    </b>
                  </li>
                  <li>
                    <span>preprocessing</span>
                    <b>{String(run.input.preprocessing)}</b>
                  </li>
                  <li>
                    <span>mode</span>
                    <b>{run.mode}</b>
                  </li>
                </ul>

                {metrics ? (
                  <>
                    <h4>How this model scores on actors it never saw</h4>
                    <ul className="audioEvidence__facts">
                      <li>
                        <span>temporal aggregation</span>
                        <b>{metrics.temporal}</b>
                      </li>
                      <li>
                        <span>test accuracy</span>
                        <b>
                          {pct(metrics.accuracy)} against a{' '}
                          {pct(metrics.baseline_accuracy)} majority baseline
                        </b>
                      </li>
                      <li>
                        <span>macro F1</span>
                        <b>
                          {metrics.macro_f1.toFixed(4)} (baseline{' '}
                          {metrics.baseline_macro_f1.toFixed(4)})
                        </b>
                      </li>
                      <li>
                        <span>weighted F1</span>
                        <b>{metrics.weighted_f1.toFixed(4)}</b>
                      </li>
                      <li>
                        <span>expected calibration error</span>
                        <b>{metrics.ece.toFixed(4)}</b>
                      </li>
                      <li>
                        <span>Brier score</span>
                        <b>{metrics.brier.toFixed(4)}</b>
                      </li>
                      <li>
                        <span>test takes / actors</span>
                        <b>
                          {metrics.samples} / {metrics.actors}
                        </b>
                      </li>
                    </ul>
                    <p className="small muted">{metrics.limitation}</p>

                    {metrics.robustness.length ? (
                      <>
                        <h4>What happens when the video is degraded</h4>
                        <p className="small muted">
                          Measured, not asserted: each corruption was applied to the frame
                          stack the model receives, and the model was never retrained on
                          any of them.
                        </p>
                        <ul className="audioEvidence__facts">
                          {metrics.robustness.map((r) => (
                            <li key={r.corruption}>
                              <span>{r.corruption.replace(/_/g, ' ')}</span>
                              <b>
                                {pct(r.accuracy)} accuracy
                                {r.corruption === 'clean'
                                  ? ''
                                  : ` (${
                                      r.accuracy - metrics.robustness[0].accuracy >= 0
                                        ? '+'
                                        : ''
                                    }${(
                                      (r.accuracy - metrics.robustness[0].accuracy) *
                                      100
                                    ).toFixed(1)} pts)`}
                              </b>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                  </>
                ) : null}
              </div>

              <p className="audioEvidence__run small muted">
                run {run.run_id} · {run.model_id} · this evidence was computed from that
                run.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

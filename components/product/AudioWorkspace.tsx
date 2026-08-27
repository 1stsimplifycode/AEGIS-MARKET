'use client';

/**
 * Analyse a speech clip: choose an input, run it, read what the model decided and why.
 *
 * A workflow rather than a card. Nothing appears here until a person picks a clip and
 * presses Analyse, and what appears is one run of AUDIO_MODEL_V1 against that input —
 * fetched from the backend, never a stored result. The run id in the footer is the one the
 * backend minted for this request.
 *
 * **Why the clips carry their annotation.** Each offered clip shows the emotion the
 * RAVDESS actor was directed to portray, before the model is run. Showing it afterwards
 * only would let the panel read as though the model were always right; showing it first
 * means a reader can watch it be wrong, which at this accuracy it often is.
 *
 * **The wording is deliberate.** The model classifies a *performance* against the dataset's
 * annotation. It does not read a speaker's inner state, and no copy here says it does.
 *
 * This is inference over a submitted clip. It is not a live or streaming capability, and
 * nothing here claims to be one.
 */
import { useCallback, useEffect, useState } from 'react';

interface Sample {
  id: string;
  speaker: string;
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
  source: {
    dataset: string;
    licence: string;
    split: string;
    split_strategy: string;
    speakers: string[];
    why_these: string;
  };
  samples: Sample[];
  error?: { reason: string; remedy: string };
}

interface Region {
  start_s: number;
  end_s: number;
  relevance: number;
}

interface Band {
  from_hz: number;
  to_hz: number;
  relevance: number;
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
  parameters: { total: number; trainable: number; frozen: number };
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
    temporal_regions: Region[];
    frequency_bands: Band[];
    spectrogram: { mels: number; frames: number; seconds_per_frame: number };
    descriptive_features: Record<string, number>;
    descriptive_features_note: string;
  };
  error?: { reason: string; remedy: string };
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function AudioWorkspace({ metrics }: { metrics: Metrics | null }) {
  const [offer, setOffer] = useState<Offer | null>(null);
  const [chosen, setChosen] = useState<string>('');
  const [upload, setUpload] = useState<{ name: string; base64: string } | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [why, setWhy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/api/aegis/multimodal/audio/samples', {
          cache: 'no-store',
        });
        const payload = (await response.json()) as Offer;
        if (cancelled) return;
        if (payload.status !== 'OK') {
          setFailure(payload.error?.reason ?? 'the clip list could not be read');
          return;
        }
        setOffer(payload);
        setChosen(payload.samples[0]?.id ?? '');
      } catch {
        if (!cancelled) setFailure('the backend is not answering');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onFile = useCallback((file: File | null) => {
    if (!file) {
      setUpload(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? '');
      setUpload({ name: file.name, base64: result.slice(result.indexOf(',') + 1) });
      setChosen('');
    };
    reader.readAsDataURL(file);
  }, []);

  const analyse = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    setWhy(false);
    try {
      const body = upload
        ? { audio_base64: upload.base64, filename: upload.name }
        : { clip: chosen };
      const response = await fetch('/api/aegis/multimodal/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const payload = (await response.json()) as Run;
      if (payload.status !== 'OK') {
        setRun(null);
        setFailure(payload.error?.reason ?? 'the analysis was refused');
        return;
      }
      setRun(payload);
    } catch {
      setRun(null);
      setFailure('the backend is not answering');
    } finally {
      setBusy(false);
    }
  }, [chosen, upload]);

  const selected = offer?.samples.find((s) => s.id === chosen) ?? null;

  return (
    <section className="home__section audioWork">
      <div className="home__sectionHead">
        <h2>Analyse a speech clip</h2>
      </div>

      <p className="home__caveat" style={{ marginTop: 0 }}>
        {offer?.task ?? 'Speech-expression classification according to the dataset annotation.'}{' '}
        The model reports which labelled performance a clip resembles. It does not measure
        anyone&rsquo;s emotional state.
      </p>

      {failure && !run ? (
        <p className="ticket__refusal" role="status">
          {failure}
        </p>
      ) : null}

      {offer ? (
        <>
          <div className="audioWork__pick">
            <label className="audioWork__field">
              <span className="audioWork__label">Held-out clip</span>
              <select
                value={chosen}
                onChange={(e) => {
                  setChosen(e.target.value);
                  setUpload(null);
                }}
              >
                {offer.samples.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.speaker} · annotated {s.annotated_as} · {s.intensity}
                  </option>
                ))}
              </select>
            </label>

            <label className="audioWork__field">
              <span className="audioWork__label">or your own audio</span>
              <input
                type="file"
                accept="audio/wav,audio/x-wav,audio/flac,.wav,.flac"
                onChange={(e) => onFile(e.target.files?.[0] ?? null)}
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
                ? `${selected.speaker} saying “${selected.spoken_text}”, annotated ${selected.annotated_as}.`
                : 'Choose a clip.'}{' '}
            <span className="modeOnly modeOnly--research modeOnly--inline">
              {offer.source.why_these} Speakers: {offer.source.speakers.join(', ')}.
            </span>
          </p>
        </>
      ) : failure ? null : (
        <p className="small muted">Loading the clips on offer…</p>
      )}

      {run ? (
        <div className="audioResult">
          <p className="audioResult__eyebrow">Audio analysed</p>

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

                  <h4>Where in the clip</h4>
                  <ul className="audioEvidence__bars">
                    {run.evidence.temporal_regions.map((r) => (
                      <li key={`${r.start_s}-${r.end_s}`}>
                        <span className="audioEvidence__span">
                          {r.start_s.toFixed(2)}–{r.end_s.toFixed(2)} s
                        </span>
                        <span className="audioEvidence__bar">
                          <span style={{ width: `${Math.min(r.relevance * 100, 100)}%` }} />
                        </span>
                        <span className="audioEvidence__num">{pct(r.relevance)}</span>
                      </li>
                    ))}
                  </ul>

                  <h4>Which frequencies</h4>
                  <ul className="audioEvidence__bars">
                    {run.evidence.frequency_bands.map((b) => (
                      <li key={b.from_hz}>
                        <span className="audioEvidence__span">
                          {b.from_hz}–{b.to_hz} Hz
                        </span>
                        <span className="audioEvidence__bar">
                          <span style={{ width: `${Math.min(b.relevance * 100, 100)}%` }} />
                        </span>
                        <span className="audioEvidence__num">{pct(b.relevance)}</span>
                      </li>
                    ))}
                  </ul>

                  <h4>Full posterior</h4>
                  <ul className="audioEvidence__bars">
                    {run.posterior.map((p) => (
                      <li key={p.class}>
                        <span className="audioEvidence__span">{p.class}</span>
                        <span className="audioEvidence__bar">
                          <span style={{ width: `${Math.min(p.probability * 100, 100)}%` }} />
                        </span>
                        <span className="audioEvidence__num">{pct(p.probability)}</span>
                      </li>
                    ))}
                  </ul>

                  <div className="modeOnly modeOnly--research">
                    <h4>Measured from the waveform</h4>
                    <p className="small muted">
                      {run.evidence.descriptive_features_note}
                    </p>
                    <ul className="audioEvidence__facts">
                      {Object.entries(run.evidence.descriptive_features).map(([k, v]) => (
                        <li key={k}>
                          <span>{k.replace(/_/g, ' ')}</span>
                          <b>{v.toFixed(4)}</b>
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : (
                <p className="small muted">
                  No attribution was computed for this run.
                </p>
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
                  {Object.entries(run.provenance).map(([k, v]) => (
                    <li key={k}>
                      <span>{k.replace(/_/g, ' ')}</span>
                      <b>{v}</b>
                    </li>
                  ))}
                  <li>
                    <span>input</span>
                    <b>
                      {String(run.input.filename ?? run.input.clip ?? 'audio')} ·{' '}
                      {String(run.input.duration_s)} s · {String(run.input.representation)}
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
                    <h4>How this model scores on speakers it never heard</h4>
                    <ul className="audioEvidence__facts">
                      <li>
                        <span>test accuracy</span>
                        <b>
                          {pct(metrics.accuracy)} against a {pct(metrics.baseline_accuracy)}{' '}
                          majority baseline
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
                        <span>test clips / speakers</span>
                        <b>
                          {metrics.samples} / {metrics.speakers}
                        </b>
                      </li>
                    </ul>
                    <p className="small muted">{metrics.limitation}</p>

                    {metrics.robustness.length ? (
                      <>
                        <h4>What happens when the audio is not clean</h4>
                        <p className="small muted">
                          Measured, not asserted: each corruption was applied to the
                          waveform and pushed through the same preprocessing the model was
                          trained on. Additive noise takes it close to the majority
                          baseline — the corpus is clean studio speech and the model was
                          never shown a noisy example.
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
                run {run.run_id} · {run.model_id} · this evidence was computed from that run.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export interface Metrics {
  accuracy: number;
  macro_f1: number;
  weighted_f1: number;
  baseline_accuracy: number;
  baseline_macro_f1: number;
  ece: number;
  brier: number;
  samples: number;
  speakers: number;
  limitation: string;
  robustness: { corruption: string; accuracy: number; macro_f1: number }[];
}

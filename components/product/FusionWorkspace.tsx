'use client';

/**
 * Analyse a paired sample with audio, video, or both — and see what each one contributed.
 *
 * The modality switches are the point of this workspace, not a setting. The experiment
 * behind it found that fusion scored *below* audio alone on held-out actors, so a panel
 * that showed only the fused answer would be presenting the weaker model as the product's
 * best. Here a person can turn a modality off and watch the answer change, on the same
 * performance, in the same run.
 *
 * Everything comes from one backend inference call. The modality split under Why is
 * computed by integrated gradients over the two embeddings during that call; nothing here
 * is a hard-coded percentage.
 *
 * The wording is the dataset's: this classifies a *performance* against the RAVDESS
 * annotation. It does not read anyone's inner state, and no copy here says it does.
 *
 * Inference over submitted samples. Not a live or streaming capability.
 */
import { useCallback, useEffect, useState } from 'react';

interface Sample {
  id: string;
  actor: string;
  annotated_as: string;
  intensity: string;
  spoken_text: string;
}

interface Metrics {
  fusion_accuracy: number;
  audio_only_accuracy: number;
  video_only_accuracy: number;
  fusion_macro_f1: number;
  expected_calibration_error: number;
  fusion_gain_over_audio: { point: number; ci_low: number; ci_high: number };
  verdict: string;
  test_pairs: number;
  test_actors: string[];
}

interface Offer {
  status: string;
  model_id: string;
  model_available: boolean;
  task: string;
  note: string;
  measured_finding: string;
  headline_metrics: Metrics;
  alignment: string;
  alignment_note: string;
  source: { actors: string[]; why_these: string; licence: string };
  samples: Sample[];
  error?: { reason: string; remedy: string };
}

interface Run {
  status: string;
  run_id: string;
  model_id: string;
  checkpoint: string;
  checkpoint_sha256: string;
  available_modalities: string[];
  missing_modalities: string[];
  predicted: string;
  confidence: number;
  uncertainty: number;
  posterior: { class: string; probability: number }[];
  per_modality: Record<
    string,
    { available: boolean; predicted: string | null;
      posterior: { class: string; probability: number }[] }
  >;
  agreement_with_annotation?: boolean;
  input: Record<string, unknown>;
  provenance: Record<string, string>;
  parameters: { trainable: number; frozen: number };
  alignment: string;
  alignment_note: string;
  measured_finding: string;
  headline_metrics: Metrics;
  mode: string;
  note: string;
  evidence?: {
    run_id: string;
    modality_attribution: {
      method: string;
      method_note: string;
      audio_share: number | null;
      video_share: number | null;
      audio_present: boolean;
      video_present: boolean;
      note: string;
    };
    audio?: {
      from_model: string; run_id: string; predicted: string; method: string;
      temporal_regions: { start_s: number; end_s: number; relevance: number }[];
    };
    video?: {
      from_model: string; run_id: string; predicted: string; method: string;
      top_frames: { index: number; at_s: number; relevance: number }[];
    };
  };
  error?: { reason: string; remedy: string };
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function FusionWorkspace() {
  const [offer, setOffer] = useState<Offer | null>(null);
  const [chosen, setChosen] = useState('');
  const [useAudio, setUseAudio] = useState(true);
  const [useVideo, setUseVideo] = useState(true);
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const [why, setWhy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ reason: string; remedy?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/api/aegis/multimodal/fusion/samples', {
          cache: 'no-store',
        });
        const payload = (await response.json()) as Offer;
        if (cancelled) return;
        if (payload.status !== 'OK') {
          setFailure({
            reason: payload.error?.reason ?? 'the sample list could not be read',
            remedy: payload.error?.remedy,
          });
          return;
        }
        setOffer(payload);
        setChosen(payload.samples[0]?.id ?? '');
      } catch {
        if (!cancelled) setFailure({ reason: 'the backend is not answering' });
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
    try {
      const use = [
        ...(useAudio ? ['audio'] : []),
        ...(useVideo ? ['video'] : []),
      ];
      const response = await fetch('/api/aegis/multimodal/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modality: 'fusion', pair: chosen, use }),
      });
      const payload = (await response.json()) as Run;
      if (payload.status !== 'OK') {
        setFailure({
          reason: payload.error?.reason ?? 'the analysis was refused',
          remedy: payload.error?.remedy,
        });
        return;
      }
      setRun(payload);
      setHistory((previous) => [payload, ...previous].slice(0, 6));
    } catch {
      setFailure({
        reason: 'the backend is not answering',
        remedy: 'Start it with run_dev.bat and try again.',
      });
    } finally {
      setBusy(false);
    }
  }, [chosen, useAudio, useVideo]);

  const selected = offer?.samples.find((s) => s.id === chosen) ?? null;
  const attribution = run?.evidence?.modality_attribution;

  return (
    <section className="home__section audioWork fusionWork">
      <div className="home__sectionHead">
        <h2>Analyse a paired sample</h2>
      </div>

      <p className="home__caveat" style={{ marginTop: 0 }}>
        {offer?.task ??
          'Audio-visual expression classification according to the dataset annotation.'}{' '}
        The model reports which labelled performance a sample resembles. It does not
        measure anyone&rsquo;s emotional state.
      </p>

      {offer ? (
        <p className="fusionWork__finding" role="note">
          <strong>What the experiment found.</strong> {offer.measured_finding}
        </p>
      ) : null}

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
              <span className="audioWork__label">Held-out performance</span>
              <select value={chosen} onChange={(e) => setChosen(e.target.value)}>
                {offer.samples.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.actor} · annotated {s.annotated_as} · {s.intensity}
                  </option>
                ))}
              </select>
            </label>

            <fieldset className="fusionWork__modalities">
              <legend className="audioWork__label">Use which modalities</legend>
              <label>
                <input
                  type="checkbox"
                  checked={useAudio}
                  onChange={(e) => setUseAudio(e.target.checked)}
                />
                Audio
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={useVideo}
                  onChange={(e) => setUseVideo(e.target.checked)}
                />
                Video
              </label>
            </fieldset>

            <button
              type="button"
              className="btn"
              onClick={() => void analyse()}
              disabled={busy || (!useAudio && !useVideo) || !chosen}
            >
              {busy ? 'Analysing…' : 'Analyse'}
            </button>
          </div>

          <p className="audioWork__context small muted">
            {!useAudio && !useVideo
              ? 'Choose at least one modality.'
              : selected
                ? `${selected.actor} saying “${selected.spoken_text}”, annotated ${selected.annotated_as}.`
                : 'Choose a performance.'}{' '}
            <span className="modeOnly modeOnly--research modeOnly--inline">
              {offer.source.why_these} Held-out actors: {offer.source.actors.join(', ')}.{' '}
              {offer.alignment_note}
            </span>
          </p>

          {busy ? (
            <p className="videoWork__progress small" role="status">
              <span className="videoWork__spinner" aria-hidden="true" />
              Decoding both modalities, running the encoders and the fusion head, and
              computing the attribution from this run.
            </p>
          ) : null}
        </>
      ) : failure ? null : (
        <p className="small muted">Loading the paired samples…</p>
      )}

      {run ? (
        <div className="audioResult">
          <p className="audioResult__eyebrow">Sample analysed</p>

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
              <span className="audioWork__label">Modalities used</span>
              <p className="audioResult__value">
                {(['audio', 'video'] as const).map((m) => (
                  <span key={m} className="fusionWork__chip" data-on={run.available_modalities.includes(m)}>
                    {run.available_modalities.includes(m) ? '✓' : '—'} {m}
                  </span>
                ))}
              </p>
            </div>
          </div>

          {typeof run.agreement_with_annotation === 'boolean' ? (
            <p className="audioResult__agreement" data-agrees={run.agreement_with_annotation}>
              {run.agreement_with_annotation
                ? `Matches the dataset annotation (${String(run.input.annotated_as)}).`
                : `Does not match the dataset annotation, which is ${String(run.input.annotated_as)}.`}
            </p>
          ) : null}

          <div className="fusionWork__compare">
            {(['audio', 'video'] as const).map((m) => (
              <div key={m} data-available={run.per_modality[m]?.available}>
                <span className="audioWork__label">{m} alone</span>
                <p className="audioResult__value">
                  {run.per_modality[m]?.available
                    ? run.per_modality[m]?.predicted
                    : 'not supplied'}
                </p>
              </div>
            ))}
            <div>
              <span className="audioWork__label">both, fused</span>
              <p className="audioResult__value">{run.predicted}</p>
            </div>
          </div>

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
              {attribution ? (
                <>
                  <h4>What each modality contributed</h4>
                  <p className="small muted">
                    {attribution.method}. {attribution.method_note}
                  </p>
                  <ul className="audioEvidence__bars">
                    {(['audio', 'video'] as const).map((m) => {
                      const share = m === 'audio'
                        ? attribution.audio_share
                        : attribution.video_share;
                      const present = m === 'audio'
                        ? attribution.audio_present
                        : attribution.video_present;
                      return (
                        <li key={m}>
                          <span className="audioEvidence__span">{m}</span>
                          <span className="audioEvidence__bar">
                            <span
                              style={{
                                width: `${Math.min((share ?? 0) * 100, 100)}%`,
                                opacity: present ? 1 : 0.35,
                              }}
                            />
                          </span>
                          <span className="audioEvidence__num">
                            {present && share !== null ? pct(share) : '—'}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  <p className="small muted">{attribution.note}</p>
                </>
              ) : null}

              {run.evidence?.audio ? (
                <>
                  <h4>Where in the audio</h4>
                  <p className="small muted">
                    {run.evidence.audio.method}, from {run.evidence.audio.from_model} run{' '}
                    {run.evidence.audio.run_id}.
                  </p>
                  <ul className="audioEvidence__bars">
                    {run.evidence.audio.temporal_regions.map((r) => (
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
                </>
              ) : null}

              {run.evidence?.video ? (
                <>
                  <h4>Which frames</h4>
                  <p className="small muted">
                    {run.evidence.video.method}, from {run.evidence.video.from_model} run{' '}
                    {run.evidence.video.run_id}.
                  </p>
                  <ul className="audioEvidence__bars">
                    {run.evidence.video.top_frames.map((f) => (
                      <li key={f.index}>
                        <span className="audioEvidence__span">{f.at_s.toFixed(2)} s</span>
                        <span className="audioEvidence__bar">
                          <span style={{ width: `${Math.min(f.relevance * 100, 100)}%` }} />
                        </span>
                        <span className="audioEvidence__num">{pct(f.relevance)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}

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

              <div className="modeOnly modeOnly--research audioEvidence__research">
                <h4>What the experiment measured</h4>
                <ul className="audioEvidence__facts">
                  <li>
                    <span>fusion accuracy</span>
                    <b>{pct(run.headline_metrics.fusion_accuracy)}</b>
                  </li>
                  <li>
                    <span>audio only</span>
                    <b>{pct(run.headline_metrics.audio_only_accuracy)}</b>
                  </li>
                  <li>
                    <span>video only</span>
                    <b>{pct(run.headline_metrics.video_only_accuracy)}</b>
                  </li>
                  <li>
                    <span>fusion gain over audio</span>
                    <b>
                      {run.headline_metrics.fusion_gain_over_audio.point.toFixed(4)} [
                      {run.headline_metrics.fusion_gain_over_audio.ci_low.toFixed(4)},{' '}
                      {run.headline_metrics.fusion_gain_over_audio.ci_high.toFixed(4)}]
                    </b>
                  </li>
                  <li>
                    <span>verdict</span>
                    <b>{run.headline_metrics.verdict}</b>
                  </li>
                  <li>
                    <span>expected calibration error</span>
                    <b>{run.headline_metrics.expected_calibration_error.toFixed(4)}</b>
                  </li>
                  <li>
                    <span>test set</span>
                    <b>
                      {run.headline_metrics.test_pairs} pairs ·{' '}
                      {run.headline_metrics.test_actors.join(', ')}
                    </b>
                  </li>
                  <li>
                    <span>alignment</span>
                    <b>{run.alignment}</b>
                  </li>
                  <li>
                    <span>checkpoint sha256</span>
                    <b>{run.checkpoint_sha256.slice(0, 24)}…</b>
                  </li>
                  <li>
                    <span>trainable parameters</span>
                    <b>{run.parameters.trainable.toLocaleString()}</b>
                  </li>
                  {Object.entries(run.provenance).map(([k, v]) => (
                    <li key={k}>
                      <span>{k.replace(/_/g, ' ')}</span>
                      <b>{v}</b>
                    </li>
                  ))}
                  <li>
                    <span>mode</span>
                    <b>{run.mode}</b>
                  </li>
                </ul>
                <p className="small muted">{run.alignment_note}</p>
              </div>

              <p className="audioEvidence__run small muted">
                run {run.run_id} · {run.model_id} · this evidence was computed from that
                run.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      {history.length > 1 ? (
        <div className="fusionWork__history">
          <h4>This session</h4>
          <ul>
            {history.map((entry) => (
              <li key={entry.run_id}>
                <span className="fusionWork__historyId">{entry.run_id}</span>
                <span>{entry.available_modalities.join(' + ') || 'none'}</span>
                <span>
                  <b>{entry.predicted}</b> at {pct(entry.confidence)}
                </span>
                <span className="small muted">
                  annotated {String(entry.input.annotated_as)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

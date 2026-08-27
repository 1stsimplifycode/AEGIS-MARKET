import { NoData } from '@/components/ui/Primitives';

/**
 * Renderers for the research-angle results produced by
 * `scripts/run_research_angles.py`.
 *
 * Shared because the same measurement appears in more than one research view: the
 * lead-time frontier belongs on both the temporal page and the XAI-adjacent discussion of
 * what the model can see, and duplicating the rendering would let the two drift.
 */

type Angles = Record<string, any>;

export function KeyValue({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <div className="tableWrap">
      <table>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <th style={{ width: 260 }}>{k}</th>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AngleTable({
  rows,
  columns,
}: {
  rows: Record<string, unknown>[];
  columns: { key: string; label: string; num?: boolean; digits?: number }[];
}) {
  if (!rows?.length) return <p className="muted small">No rows.</p>;
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.num ? 'num' : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => {
                const v = r[c.key];
                const text =
                  typeof v === 'number'
                    ? Number.isFinite(v)
                      ? v.toFixed(c.digits ?? 4)
                      : 'n/a'
                    : v === null || v === undefined
                      ? 'n/a'
                      : String(v);
                return (
                  <td key={c.key} className={c.num ? 'num' : undefined}>
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LeadTimeSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N03-1'];
  if (!a) return <NoData what="Lead-time analysis" />;
  const r = a.frontier_range ?? {};
  return (
    <section>
      <h2>Detection timing (EXP-N03-1)</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        The headline lead-time number cannot say whether lateness is a tuning choice or a
        property of the evidence. Sweeping the entry threshold answers it.
      </p>
      <KeyValue
        rows={[
          [
            'Any operating point with positive lead time',
            a.any_positive_lead_operating_point ? 'yes' : 'no — none across the sweep',
          ],
          [
            'Median lead time range',
            `${r.median_lead_time_min} to ${r.median_lead_time_max} sessions`,
          ],
          [
            'Window precision range',
            `${(r.window_precision_min ?? 0).toFixed(3)} to ${(r.window_precision_max ?? 0).toFixed(3)}`,
          ],
        ]}
      />

      <h3>Modality lead and lag</h3>
      <p className="small muted">
        Cross-correlation of each modality score against the episode indicator, per
        instrument and averaged. Positive lag means the modality moves first.
      </p>
      <AngleTable
        rows={a.modality_lead_lag ?? []}
        columns={[
          { key: 'modality', label: 'Modality' },
          { key: 'peak_lag_sessions', label: 'Peak lag', num: true, digits: 0 },
          { key: 'peak_correlation', label: 'Peak corr', num: true, digits: 3 },
          { key: 'correlation_at_zero', label: 'Corr at lag 0', num: true, digits: 3 },
          { key: 'interpretation', label: 'Reading' },
        ]}
      />

      {a.lifecycle?.status === 'OK' ? (
        <>
          <h3>Lifecycle sub-tasks scored separately</h3>
          <p className="small muted">
            Onset, peak and resolution are different problems with different difficulty.
            Collapsing them into one detection score hides that.
          </p>
          <AngleTable
            rows={[a.lifecycle.onset, a.lifecycle.resolution].filter(Boolean)}
            columns={[
              { key: 'task', label: 'Task' },
              { key: 'n', label: 'n', num: true, digits: 0 },
              { key: 'median_error_days', label: 'Median error (days)', num: true, digits: 1 },
              { key: 'mean_abs_error_days', label: 'Mean abs error', num: true, digits: 1 },
              { key: 'within_3_days', label: 'Within 3 days', num: true, digits: 3 },
            ]}
          />
          <p className="small muted">{a.lifecycle.note}</p>
        </>
      ) : null}
    </section>
  );
}

export function CalibrationSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-L10-1'];
  if (!a) return null;
  return (
    <section>
      <h2>Calibration under uncertainty (EXP-L10-1)</h2>
      <AngleTable
        rows={(a.by_uncertainty ?? []).filter((r: any) => r.status === 'OK')}
        columns={[
          { key: 'bucket_low', label: 'Uncertainty from', num: true, digits: 3 },
          { key: 'bucket_high', label: 'to', num: true, digits: 3 },
          { key: 'n', label: 'n', num: true, digits: 0 },
          { key: 'ece', label: 'ECE', num: true },
          { key: 'brier', label: 'Brier', num: true },
          { key: 'auprc', label: 'AUPRC', num: true },
        ]}
      />
      <p className="small">
        <strong>Slope of ECE against uncertainty:</strong>{' '}
        {a.ece_slope_vs_uncertainty?.toFixed?.(3) ?? 'n/a'} — calibration degrades exactly
        where the model reports being unsure, which is the behaviour an uncertainty
        estimate should show.
      </p>
      <p className="small muted">
        <strong>Coverage:</strong>{' '}
        {a.coverage_measurable ? 'measurable' : 'NOT MEASURABLE on this dataset'}.{' '}
        {a.coverage_note}
      </p>
    </section>
  );
}

export function SelectiveRiskSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N04-1'];
  if (!a || a.status !== 'MEASURED') return null;
  return (
    <section>
      <h2>Selective risk (EXP-N04-1)</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        The uncertainty-weighted fusion arm shows no AUPRC advantage. Judged on the metric
        that matches its purpose — error rate when the least certain rows are set aside —
        the ordering reverses.
      </p>
      <AngleTable
        rows={a.table ?? []}
        columns={[
          { key: 'coverage', label: 'Coverage', num: true, digits: 2 },
          { key: 'selective_risk_static', label: 'Static', num: true },
          { key: 'selective_risk_unc', label: 'Uncertainty-weighted', num: true },
          { key: 'risk_delta', label: 'Delta', num: true },
        ]}
      />
      <p className="small muted">{a.note}</p>
    </section>
  );
}

export function PowerSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-L12-1'];
  if (!a) return null;
  return (
    <section>
      <h2>Statistical power (EXP-L12-1)</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        A non-significant difference is only informative if the study could have detected
        a difference worth caring about. The minimum detectable effect is the
        bootstrap interval half-width at the full episode count.
      </p>
      <AngleTable
        rows={a.comparisons ?? []}
        columns={[
          { key: 'arm', label: 'Comparison' },
          { key: 'prior_label', label: 'Reported as' },
          {
            key: 'minimum_detectable_effect',
            label: 'Min detectable effect',
            num: true,
            digits: 6,
          },
          { key: 'observed_difference', label: 'Observed', num: true, digits: 6 },
          { key: 'informative', label: 'Informative' },
          { key: 'scaling_exponent', label: 'Scaling exponent', num: true, digits: 3 },
        ]}
      />
      <p className="small muted">
        The textbook exponent is -0.5. Measured exponents near it indicate the bootstrap
        is behaving as expected under clustering.
      </p>
    </section>
  );
}

export function LimeStabilitySection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N01-1'];
  if (!a || a.status !== 'MEASURED') return null;
  return (
    <section>
      <h2>Explanation stability against cost (EXP-N01-1)</h2>
      <AngleTable
        rows={a.table ?? []}
        columns={[
          { key: 'n_perturbations', label: 'Perturbations', num: true, digits: 0 },
          { key: 'sign_consistency', label: 'Sign consistency', num: true, digits: 3 },
          { key: 'passes_threshold', label: 'Passes 0.80' },
          {
            key: 'spearman_vs_occlusion',
            label: 'Rank corr vs occlusion',
            num: true,
            digits: 3,
          },
          { key: 'seconds_per_run', label: 'Seconds', num: true, digits: 3 },
        ]}
      />
      <p className="small">
        Crosses the pre-declared threshold at {a.crosses_threshold_at ?? 'n/a'}{' '}
        perturbations, still cheaper than occlusion (
        {a.occlusion_seconds?.toFixed?.(3)} s). Its rank correlation against occlusion
        stays near zero throughout: <strong>stability is not agreement</strong>. Two
        methods can each be reproducible and still rank features differently.
      </p>
    </section>
  );
}

export function RegimeSection({ angles }: { angles: Angles }) {
  const a = angles?.['EXP-N02-1'];
  if (!a || a.status !== 'MEASURED') return null;
  return (
    <section>
      <h2>Why regime conditioning underperforms (EXP-N02-1)</h2>
      <KeyValue
        rows={[
          [
            'Gap trend per additional episode cluster',
            a.gap_trend_per_cluster?.toExponential?.(2) ?? 'n/a',
          ],
          [
            'Gap narrows as sample grows',
            a.gap_shrinks_with_sample ? 'yes — consistent with variance inflation' : 'no',
          ],
          [
            'Episodes per regime (validation)',
            JSON.stringify(a.episodes_per_regime_validation ?? {}),
          ],
        ]}
      />
      <p className="small muted">{a.interpretation_rule}</p>
    </section>
  );
}

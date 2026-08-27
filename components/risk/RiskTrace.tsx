import { Trace } from '@/components/visualization/Sparkline';
import type { RiskAssessment, RiskWindow } from '@/lib/types';

/**
 * The integrity-risk trace for one instrument, with the uncertainty band, any risk windows
 * shaded, and the state-machine thresholds marked.
 *
 * The thresholds are drawn because a score of 0.5 means nothing without them: the reader
 * needs to see where entry and exit sit to interpret the shape.
 */
export function RiskTrace({
  series,
  windows = [],
  enterThreshold = 0.55,
  exitThreshold = 0.4,
}: {
  series: RiskAssessment[];
  windows?: RiskWindow[];
  enterThreshold?: number;
  exitThreshold?: number;
}) {
  if (series.length < 2) {
    return <p className="muted">Not enough observations to draw a trace.</p>;
  }
  const dates = series.map((r) => r.date);
  const values = series.map((r) => r.integrityRisk);
  const spread = series.map((r) => r.uncertainty);

  const bands = windows.map((w) => ({
    from: w.tEntry,
    to: w.tExit,
    color: '#d55e00',
    label: w.censored ? 'unresolved window' : 'risk window',
  }));

  const markers = windows.flatMap((w) => {
    const m = [{ at: w.tPeak, label: 'peak', color: '#7a0000', dash: '2 2' }];
    if (w.tExit) m.push({ at: w.tExit, label: 'exit', color: '#0072b2', dash: '5 2' });
    return m;
  });

  return (
    <Trace
      dates={dates}
      values={values}
      spread={spread}
      bands={bands}
      markers={markers}
      hlines={[
        { at: enterThreshold, label: `entry ${enterThreshold}` },
        { at: exitThreshold, label: `exit ${exitThreshold}` },
      ]}
      height={190}
      label="Integrity risk with uncertainty band; shaded regions are risk windows"
    />
  );
}

export default RiskTrace;

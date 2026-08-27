'use client';

/**
 * The controls a module declares, drawn from the same schema the backend validates with.
 *
 * `backend/registry.py` range-checks every one of these fields on arrival, and the bounds
 * it enforces are the bounds rendered here — the `min`, `max` and option list on each
 * control come from the exported schema, not from a copy in this file. A field the form
 * lets someone fill in but the service will reject is a small dishonesty that costs a
 * round trip and a confusing error, so the two are the same declaration.
 *
 * Client validation is a convenience, never the guarantee. The service revalidates
 * everything; nothing here is trusted downstream.
 */
import { useState } from 'react';

import type { InputSpec } from '@/lib/runTypes';

export type Values = Record<string, unknown>;

export function Controls({
  inputs,
  values,
  onChange,
  disabled,
  idPrefix,
}: {
  inputs: InputSpec[];
  values: Values;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  idPrefix: string;
}) {
  if (inputs.length === 0) {
    return (
      <p className="small muted">
        This module takes no parameters: it runs over the whole of its declared input.
      </p>
    );
  }
  return (
    <div className="runControls">
      {inputs.map((spec) => (
        <Field
          key={spec.name}
          spec={spec}
          value={values[spec.name]}
          onChange={onChange}
          disabled={disabled}
          id={`${idPrefix}-${spec.name}`}
        />
      ))}
    </div>
  );
}

function Field({
  spec,
  value,
  onChange,
  disabled,
  id,
}: {
  spec: InputSpec;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  id: string;
}) {
  const described = spec.note ? `${id}-note` : undefined;
  return (
    <div className="runControls__field">
      <label className="runControls__label" htmlFor={id}>
        {spec.label}
        {spec.required ? <span aria-hidden="true"> *</span> : null}
      </label>
      <Input
        spec={spec}
        value={value}
        onChange={onChange}
        disabled={disabled}
        id={id}
        describedBy={described}
      />
      {spec.note ? (
        <p className="runControls__note" id={described}>
          {spec.note}
        </p>
      ) : null}
    </div>
  );
}

function Input({
  spec,
  value,
  onChange,
  disabled,
  id,
  describedBy,
}: {
  spec: InputSpec;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  id: string;
  describedBy?: string;
}) {
  const common = { id, disabled, 'aria-describedby': describedBy } as const;

  switch (spec.kind) {
    case 'date':
      return (
        <input
          {...common}
          type="date"
          value={typeof value === 'string' ? value : ''}
          min={typeof spec.minimum === 'string' ? spec.minimum : undefined}
          max={typeof spec.maximum === 'string' ? spec.maximum : undefined}
          onChange={(e) => onChange(spec.name, e.target.value)}
        />
      );

    case 'int':
    case 'float':
      return (
        <input
          {...common}
          type="number"
          inputMode={spec.kind === 'int' ? 'numeric' : 'decimal'}
          step={spec.kind === 'int' ? 1 : 'any'}
          value={typeof value === 'number' || typeof value === 'string' ? String(value) : ''}
          min={typeof spec.minimum === 'number' ? spec.minimum : undefined}
          max={typeof spec.maximum === 'number' ? spec.maximum : undefined}
          onChange={(e) =>
            onChange(spec.name, e.target.value === '' ? '' : Number(e.target.value))
          }
        />
      );

    case 'bool':
      return (
        <span className="runControls__switch">
          <input
            {...common}
            type="checkbox"
            checked={value === true}
            onChange={(e) => onChange(spec.name, e.target.checked)}
          />
        </span>
      );

    case 'select':
      return (
        <select
          {...common}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(spec.name, e.target.value)}
        >
          {spec.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      );

    case 'multiselect':
      return (
        <div className="runControls__checks" id={id} aria-describedby={describedBy}>
          {spec.options.map((o) => {
            const list = Array.isArray(value) ? (value as string[]) : [];
            return (
              <label key={o} className="runControls__check">
                <input
                  type="checkbox"
                  disabled={disabled}
                  checked={list.includes(o)}
                  onChange={(e) =>
                    onChange(
                      spec.name,
                      e.target.checked ? [...list, o] : list.filter((v) => v !== o),
                    )
                  }
                />
                <span>{o}</span>
              </label>
            );
          })}
        </div>
      );

    case 'symbols':
      return (
        <input
          {...common}
          type="text"
          autoComplete="off"
          spellCheck={false}
          placeholder="all instruments"
          value={Array.isArray(value) ? (value as string[]).join(', ') : String(value ?? '')}
          onChange={(e) =>
            onChange(
              spec.name,
              e.target.value
                .split(',')
                .map((s) => s.trim().toUpperCase())
                .filter(Boolean),
            )
          }
        />
      );

    case 'text':
      return (
        <textarea
          {...common}
          rows={4}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(spec.name, e.target.value)}
        />
      );

    case 'document':
      return (
        <DocumentField
          spec={spec}
          value={typeof value === 'string' ? value : ''}
          onChange={onChange}
          disabled={disabled}
          id={id}
          describedBy={describedBy}
        />
      );

    default:
      return (
        <p className="small muted">
          This build does not know how to render a {spec.kind} control.
        </p>
      );
  }
}


/**
 * A text box with a file picker beside it.
 *
 * The file is sent to the service, which validates its type, size and encoding and sends
 * back the text; the text then travels as an ordinary parameter and is validated again
 * with everything else. Nothing is stored at either end, and this component never reads
 * the file itself — a second decoder here would be a second set of limits to disagree
 * with the first.
 */
function DocumentField({
  spec,
  value,
  onChange,
  disabled,
  id,
  describedBy,
}: {
  spec: InputSpec;
  value: string;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  id: string;
  describedBy?: string;
}) {
  const [status, setStatus] = useState<string>('');
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    setStatus(`Reading ${file.name}…`);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/aegis/uploads/text', { method: 'POST', body: form });
      const payload = (await res.json()) as {
        text?: string;
        filename?: string;
        characters?: number;
        truncated?: boolean;
        error?: { reason: string; remedy: string };
      };
      if (!res.ok || payload.error) {
        setStatus(
          payload.error ? `${payload.error.reason}. ${payload.error.remedy}` : 'Not read.',
        );
        return;
      }
      onChange(spec.name, payload.text ?? '');
      setStatus(
        `${payload.filename ?? 'document'}: ${payload.characters ?? 0} characters loaded` +
          (payload.truncated ? ', truncated to the extractor’s ceiling' : '') +
          '. Nothing was stored.',
      );
    } catch {
      setStatus('The document could not be read. Paste the text instead.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="runControls__document">
      <textarea
        id={id}
        aria-describedby={describedBy}
        disabled={disabled || busy}
        rows={5}
        placeholder="paste text here, or choose a plain-text file"
        value={value}
        onChange={(e) => onChange(spec.name, e.target.value)}
      />
      <div className="runControls__documentRow">
        <input
          type="file"
          accept=".txt,.md,.csv,.text,.log,text/plain"
          disabled={disabled || busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            e.target.value = '';
          }}
        />
        {value ? (
          <button
            type="button"
            className="runPanel__reset"
            disabled={disabled || busy}
            onClick={() => {
              onChange(spec.name, '');
              setStatus('');
            }}
          >
            Clear text
          </button>
        ) : null}
      </div>
      {status ? <p className="runControls__note">{status}</p> : null}
    </div>
  );
}

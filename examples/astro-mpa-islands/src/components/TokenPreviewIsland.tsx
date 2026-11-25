import { useState } from 'react';

interface Preset {
  id: string;
  brand: string;
  polarity: string;
  ground: string;
  accent: string;
  ratio: string;
}

const PRESETS: Preset[] = [
  {
    id: 'danmercede',
    brand: 'danmercede.com',
    polarity: 'dark',
    ground: '#020B29',
    accent: '#E68249',
    ratio: '7.07:1'
  },
  {
    id: 'workcue',
    brand: 'useworkcue.com (remediated)',
    polarity: 'light',
    ground: '#FBF7F0',
    accent: '#A84919',
    ratio: '5.78:1'
  },
  {
    id: 'cosmocrat',
    brand: 'cosmocrat.ai',
    polarity: 'dark',
    ground: '#0B1120',
    accent: '#F59E0B',
    ratio: '9.12:1'
  }
];

export default function TokenPreviewIsland() {
  const [selectedId, setSelectedId] = useState<string>('danmercede');
  const current = PRESETS.find((p) => p.id === selectedId) ?? PRESETS[0];

  return (
    <div className="rounded-lg border border-[var(--color-orion-border)] bg-[var(--color-orion-surface)] p-6 space-y-5">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Brand token presets">
        {PRESETS.map((preset) => {
          const active = preset.id === current.id;
          return (
            <button
              key={preset.id}
              type="button"
              aria-pressed={active}
              onClick={() => setSelectedId(preset.id)}
              className={
                active
                  ? 'min-h-[44px] rounded bg-[var(--color-orion-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-orion-accent-fg)] cursor-pointer'
                  : 'min-h-[44px] rounded border border-[var(--color-orion-border)] bg-[var(--color-orion-surface-elevated)] px-4 py-2 text-sm font-medium text-[var(--color-orion-fg)] cursor-pointer'
              }
            >
              {preset.brand}
            </button>
          );
        })}
      </div>

      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3 font-mono text-xs">
        <div className="rounded border border-[var(--color-orion-border)] bg-[var(--color-orion-bg)] p-4">
          <dt className="text-[var(--color-orion-fg-muted)] uppercase">Ground Token</dt>
          <dd className="mt-1 m-0 text-base font-semibold text-white">{current.ground}</dd>
        </div>
        <div className="rounded border border-[var(--color-orion-border)] bg-[var(--color-orion-bg)] p-4">
          <dt className="text-[var(--color-orion-fg-muted)] uppercase">Primary Accent</dt>
          <dd className="mt-1 m-0 text-base font-semibold text-white">{current.accent}</dd>
        </div>
        <div className="rounded border border-[var(--color-orion-border)] bg-[var(--color-orion-bg)] p-4">
          <dt className="text-[var(--color-orion-fg-muted)] uppercase">CTA WCAG 2.1</dt>
          <dd className="mt-1 m-0 text-base font-semibold text-[var(--color-orion-accent)]">
            {current.ratio} ({current.polarity})
          </dd>
        </div>
      </dl>
    </div>
  );
}

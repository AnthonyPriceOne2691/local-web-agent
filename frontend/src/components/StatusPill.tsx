import type { Tone } from '../copy';

/** Оттенки по смыслу, а не по названию статуса: «нужен человек» всегда янтарный,
 *  «работает» всегда акцентный, что бы бэкенд ни прислал.
 *
 *  Цвет берётся из статусных чернил (`--status-*-ink`), а не из самого акцента:
 *  акцент рассчитан на плотную кнопку, а на полупрозрачной пилюле поверх
 *  насыщенного полотна он сливался с фоном — «Visiting sites» читался с трудом.
 *  Заодно у пилюли появляется своя лёгкая подложка того же тона: она отделяет
 *  текст от полотна, не превращая пилюлю в кнопку. */
const TONE: Record<Tone, { ink: string; tint: string }> = {
  neutral: { ink: 'var(--ink-soft)', tint: 'transparent' },
  busy: { ink: 'var(--status-accent-ink)', tint: 'var(--color-accent)' },
  good: { ink: 'var(--status-mint-ink)', tint: 'var(--color-mint)' },
  warn: { ink: 'var(--status-amber-ink)', tint: 'var(--color-amber-warm)' },
  attention: { ink: 'var(--status-amber-ink)', tint: 'var(--color-amber-warm)' },
  bad: { ink: 'var(--status-rose-ink)', tint: 'var(--color-rose-warm)' },
};

interface Props {
  label: string;
  tone: Tone;
  /** Пульсирующая точка — только когда что-то реально происходит. */
  live?: boolean;
}

export default function StatusPill({ label, tone, live }: Props) {
  const { ink, tint } = TONE[tone];
  return (
    <span
      className="glass-quiet inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
      style={{
        color: ink,
        background:
          tint === 'transparent'
            ? undefined
            : `color-mix(in oklab, ${tint} 16%, var(--glass-fill-quiet))`,
        borderColor:
          tint === 'transparent'
            ? undefined
            : `color-mix(in oklab, ${tint} 32%, var(--glass-edge))`,
      }}
    >
      <span
        aria-hidden
        className={`size-1.5 shrink-0 rounded-full bg-current ${live ? 'animate-breathe' : ''}`}
      />
      {label}
    </span>
  );
}

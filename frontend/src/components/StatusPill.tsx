import type { Tone } from '../copy';

/** Оттенки по смыслу, а не по названию статуса: «нужен человек» всегда янтарный,
 *  «работает» всегда акцентный, что бы бэкенд ни прислал. */
const TONE: Record<Tone, string> = {
  neutral: 'text-soft',
  busy: 'text-[var(--color-accent)]',
  good: 'text-[var(--color-mint)]',
  warn: 'text-[var(--color-amber-warm)]',
  attention: 'text-[var(--color-amber-warm)]',
  bad: 'text-[var(--color-rose-warm)]',
};

interface Props {
  label: string;
  tone: Tone;
  /** Пульсирующая точка — только когда что-то реально происходит. */
  live?: boolean;
}

export default function StatusPill({ label, tone, live }: Props) {
  return (
    <span
      className={`glass-quiet inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${TONE[tone]}`}
    >
      <span
        aria-hidden
        className={`size-1.5 rounded-full bg-current ${live ? 'animate-pulse' : ''}`}
      />
      {label}
    </span>
  );
}

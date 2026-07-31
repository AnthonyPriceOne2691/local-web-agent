import { pauseCopy, siteName } from '../copy';
import type { ChallengeWait } from '../types';

/** Пауза, когда без человека дальше нельзя. Формулировки — в `copy.ts`: карточка
 *  отвечает за вид, а не за слова. */
export default function ChallengeCard({
  challenge,
  onResume,
}: {
  challenge: ChallengeWait;
  onResume: () => void;
}) {
  const copy = pauseCopy(challenge.kind, challenge.action);
  return (
    <div className="glass rounded-3xl border-[color-mix(in_oklab,var(--color-amber-warm)_45%,var(--glass-edge))] px-4 py-3.5">
      <div className="flex items-center gap-2">
        <span aria-hidden className="text-[var(--color-amber-warm)]">
          ⏸
        </span>
        <h2 className="text-[14px] font-semibold">{copy.title}</h2>
        <span className="text-faint ml-auto shrink-0 text-[11px]">
          {siteName(challenge.start_url)}
        </span>
      </div>
      <p className="text-soft mt-2 text-[13px] leading-relaxed">{copy.body}</p>
      <button
        onClick={onResume}
        className="btn-accent focus-ring mt-3 rounded-full px-4 py-2 text-[13px] font-medium"
      >
        {copy.button}
      </button>
    </div>
  );
}

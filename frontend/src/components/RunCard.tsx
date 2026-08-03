import { type CSSProperties, useState } from 'react';

import { api } from '../api';
import { goalLabel, pagesRead, siteName, siteState, stepLabel, wordCount } from '../copy';
import type { CrawlStep, RunRecord } from '../types';

import StatusPill from './StatusPill';

interface Shot {
  step: CrawlStep;
  pos: number;
}

/** Один сайт: что агент искал, что нашёл и как шёл. Шаги показаны фразами
 *  («Pulled the answer from this page»), а не кодами состояний.
 *
 *  Раскрытие — одно действие на всю карточку: разворачивается и полный текст итога
 *  (раньше он был обрезан насовсем и прочитать его было нельзя), и шаги. Высота
 *  анимируется утилитами `reveal`/`clamp-soft`, а не скачком. */
export default function RunCard({ run }: { run: RunRecord }) {
  const [open, setOpen] = useState(false);
  const shots: Shot[] = run.steps
    .map((step, pos) => ({ step, pos }))
    .filter(({ step }) => Object.keys(step.screenshot_paths).length > 0);
  // Раскрывать нечего — кнопки нет: неработающая кнопка хуже отсутствующей.
  const expandable = Boolean(
    run.steps.length || run.result?.article || (run.result?.summary?.length ?? 0) > 150,
  );

  return (
    <div className="glass-quiet rise-in overflow-hidden rounded-2xl">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        disabled={!expandable}
        className="focus-ring press block w-full px-3.5 py-3 text-left disabled:cursor-default"
      >
        <RunHeading run={run} open={open} expandable={expandable} />
        {run.result?.summary && (
          <p
            data-open={open ? 'true' : 'false'}
            className="text-soft clamp-soft mt-1.5 text-[12px] leading-relaxed"
          >
            {run.result.summary}
          </p>
        )}
        {run.error_message && (
          <p
            data-open={open ? 'true' : 'false'}
            className="clamp-soft mt-1.5 text-[12px] text-[var(--color-rose-warm)]"
            style={{ '--clamp-lines': 2 } as CSSProperties}
          >
            {run.error_message}
          </p>
        )}
        {!open && expandable && (
          <span className="text-faint mt-1.5 block text-[11px] font-medium">Show details</span>
        )}
      </button>

      <div className="reveal" data-open={open ? 'true' : 'false'} aria-hidden={!open}>
        <div className="space-y-3 border-t border-[var(--glass-edge)] px-3.5 py-3">
          {shots.length > 0 && <RunShots runId={run.id} shots={shots} />}
          {run.steps.length > 0 && <RunSteps steps={run.steps} />}
          {run.result?.article && (
            <div className="glass rounded-xl px-3 py-2.5 text-[12px]">
              <div className="font-medium">{run.result.article.title || 'Article found'}</div>
              <div className="text-faint mt-0.5">
                {wordCount(run.result.article.word_count)} · {siteName(run.result.article.url)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RunHeading({
  run,
  open,
  expandable,
}: {
  run: RunRecord;
  open: boolean;
  expandable: boolean;
}) {
  const state = siteState(run.status);
  return (
    <>
      <div className="flex items-center gap-2">
        <StatusPill label={state.text} tone={state.tone} live={state.tone === 'busy'} />
        <span className="text-faint ml-auto shrink-0 text-[11px]">
          {pagesRead(run.pages_visited, run.config.max_pages)}
        </span>
        {expandable && <Chevron open={open} />}
      </div>
      <div className="mt-2 truncate text-[13px] font-medium">{siteName(run.config.start_url)}</div>
      <div className="text-faint mt-0.5 text-[11px]">{goalLabel(run.intent)}</div>
    </>
  );
}

/** Стрелка поворачивается — направление раскрытия видно до нажатия. */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden
      className="text-faint size-3.5 shrink-0 transition-transform duration-300"
      style={{ transform: open ? 'rotate(180deg)' : undefined }}
    >
      <path
        d="M4 6.5 8 10.5l4-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function RunShots({ runId, shots }: { runId: string; shots: Shot[] }) {
  return (
    <div className="scroll-slim flex gap-2 overflow-x-auto pb-1">
      {shots.map(({ step, pos }) => {
        const profile = step.screenshot_paths.desktop
          ? 'desktop'
          : Object.keys(step.screenshot_paths)[0];
        const url = api.screenshotUrl(runId, pos, profile);
        return (
          <a key={pos} href={url} target="_blank" rel="noreferrer" className="focus-ring shrink-0">
            <img
              src={url}
              loading="lazy"
              alt={`What the agent saw: ${stepLabel(step).toLowerCase()}`}
              className="h-24 rounded-xl border border-[var(--glass-edge)] transition-transform duration-200 hover:scale-[1.03]"
            />
          </a>
        );
      })}
    </div>
  );
}

function RunSteps({ steps }: { steps: CrawlStep[] }) {
  return (
    <div>
      <h3 className="text-faint mb-1.5 text-[11px] font-medium tracking-wide uppercase">
        How it got there
      </h3>
      <ol className="space-y-1">
        {steps.map((step, pos) => (
          <li key={pos} className="flex gap-2 text-[12px]">
            {/* Считаем с единицы: step.index — индекс из бэкенда, у людей списки с 1 */}
            <span className="text-faint w-4 shrink-0 tabular-nums">{pos + 1}</span>
            <span className="shrink-0">{stepLabel(step)}</span>
            {(step.target_url || step.note) && (
              <span className="text-faint truncate">{step.target_url || step.note}</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

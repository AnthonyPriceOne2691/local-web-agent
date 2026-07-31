import { useState } from 'react';

import { api } from '../api';
import { goalLabel, pagesRead, siteName, siteState, stepLabel, wordCount } from '../copy';
import type { RunRecord } from '../types';

import StatusPill from './StatusPill';

/** Один сайт: что агент искал, что нашёл и как шёл. Шаги показаны фразами
 *  («Pulled the answer from this page»), а не кодами состояний. */
export default function RunCard({ run }: { run: RunRecord }) {
  const [open, setOpen] = useState(false);
  const state = siteState(run.status);
  const shots = run.steps
    .map((step, pos) => ({ step, pos }))
    .filter(({ step }) => Object.keys(step.screenshot_paths).length > 0);

  return (
    <div className="glass-quiet overflow-hidden rounded-2xl">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="focus-ring block w-full px-3.5 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <StatusPill label={state.text} tone={state.tone} live={state.tone === 'busy'} />
          <span className="text-faint ml-auto shrink-0 text-[11px]">
            {pagesRead(run.pages_visited, run.config.max_pages)}
          </span>
        </div>
        <div className="mt-2 truncate text-[13px] font-medium">
          {siteName(run.config.start_url)}
        </div>
        <div className="text-faint mt-0.5 text-[11px]">{goalLabel(run.intent)}</div>
        {run.result?.summary && (
          <p className="text-soft mt-1.5 line-clamp-3 text-[12px] leading-relaxed">
            {run.result.summary}
          </p>
        )}
        {run.error_message && (
          <p className="mt-1.5 line-clamp-2 text-[12px] text-[var(--color-rose-warm)]">
            {run.error_message}
          </p>
        )}
      </button>

      {open && (
        <div className="space-y-3 border-t border-[var(--glass-edge)] px-3.5 py-3">
          {shots.length > 0 && (
            <div className="scroll-slim flex gap-2 overflow-x-auto pb-1">
              {shots.map(({ step, pos }) => {
                const profile = step.screenshot_paths.desktop
                  ? 'desktop'
                  : Object.keys(step.screenshot_paths)[0];
                const url = api.screenshotUrl(run.id, pos, profile);
                return (
                  <a
                    key={pos}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring shrink-0"
                  >
                    <img
                      src={url}
                      loading="lazy"
                      alt={`What the agent saw: ${stepLabel(step).toLowerCase()}`}
                      className="h-24 rounded-xl border border-[var(--glass-edge)]"
                    />
                  </a>
                );
              })}
            </div>
          )}

          <div>
            <h3 className="text-faint mb-1.5 text-[11px] font-medium tracking-wide uppercase">
              How it got there
            </h3>
            <ol className="space-y-1">
              {run.steps.map((step, pos) => (
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

          {run.result?.article && (
            <div className="glass rounded-xl px-3 py-2.5 text-[12px]">
              <div className="font-medium">{run.result.article.title || 'Article found'}</div>
              <div className="text-faint mt-0.5">
                {wordCount(run.result.article.word_count)} · {siteName(run.result.article.url)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

import { useState } from 'react';
import { api } from '../api';
import type { RunRecord } from '../types';
import StatusBadge from './StatusBadge';

export default function RunCard({ run }: { run: RunRecord }) {
  const [open, setOpen] = useState(false);
  const shots = run.steps
    .map((step, pos) => ({ step, pos }))
    .filter(({ step }) => Object.keys(step.screenshot_paths).length > 0);

  return (
    <div className="rounded-lg border border-slate-200 bg-white text-xs">
      <button onClick={() => setOpen(!open)} className="w-full text-left p-3">
        <div className="flex items-center gap-2">
          <StatusBadge status={run.status} />
          <span className="text-slate-400">{run.intent}</span>
          <span className="ml-auto text-slate-400">{run.pages_visited} pages</span>
        </div>
        <div className="mt-1.5 font-medium text-slate-800 truncate">{run.config.start_url}</div>
        {run.result?.summary && (
          <div className="mt-1 text-slate-500 line-clamp-2">{run.result.summary}</div>
        )}
        {run.error_message && (
          <div className="mt-1 text-red-600 line-clamp-2">{run.error_message}</div>
        )}
      </button>

      {open && (
        <div className="border-t border-slate-100 p-3 space-y-2">
          {shots.length > 0 && (
            <div className="flex gap-1.5 overflow-x-auto pb-1">
              {shots.map(({ step, pos }) => {
                const profile = step.screenshot_paths.desktop
                  ? 'desktop'
                  : Object.keys(step.screenshot_paths)[0];
                const url = api.screenshotUrl(run.id, pos, profile);
                return (
                  <a key={pos} href={url} target="_blank" rel="noreferrer" className="shrink-0">
                    <img
                      src={url}
                      loading="lazy"
                      alt={`step ${step.index} ${profile}`}
                      className="h-20 rounded border border-slate-200 hover:border-blue-400"
                    />
                  </a>
                );
              })}
            </div>
          )}
          <ol className="space-y-1">
            {run.steps.map((step, pos) => (
              <li key={pos} className="flex gap-2 items-baseline">
                <span className="text-slate-300 tabular-nums w-4 shrink-0">{step.index}</span>
                <span className="font-mono text-slate-600 shrink-0">
                  {step.action || step.state.toLowerCase()}
                </span>
                <span className="truncate text-slate-400">
                  {step.target_url || step.note || step.url}
                </span>
              </li>
            ))}
          </ol>
          {run.result?.article && (
            <div className="rounded bg-slate-50 p-2">
              <span className="font-medium">Article:</span> {run.result.article.title}{' '}
              <span className="text-slate-400">({run.result.article.word_count} words)</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

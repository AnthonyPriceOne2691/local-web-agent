import { useState } from 'react';

import type { CrawlProgress, RunRecord, SessionRecord } from '../types';

import ComparisonView from './ComparisonView';
import RunCard from './RunCard';

interface Props {
  session: SessionRecord | null;
  runs: Record<string, RunRecord>;
  progress: CrawlProgress | null;
}

export default function SidePanel({ session, runs, progress }: Props) {
  const [tab, setTab] = useState<'runs' | 'comparison'>('runs');
  if (!session) return null;
  const hasComparison = session.comparison_result != null;
  const active = tab === 'comparison' && hasComparison ? 'comparison' : 'runs';

  return (
    <aside className="w-[380px] shrink-0 border-l border-slate-200 bg-slate-50 flex flex-col">
      <div className="h-12 shrink-0 border-b border-slate-200 bg-white flex items-center px-2 gap-1">
        <TabButton
          label={`Runs (${session.run_ids.length})`}
          active={active === 'runs'}
          onClick={() => setTab('runs')}
        />
        <TabButton
          label="Comparison"
          active={active === 'comparison'}
          disabled={!hasComparison}
          onClick={() => setTab('comparison')}
        />
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {active === 'runs' && (
          <>
            {progress && !session.run_ids.includes(progress.run_id) && (
              <div className="rounded-lg border border-blue-200 bg-white p-3 text-xs">
                <div className="font-medium text-blue-700 mb-1">● Crawling now</div>
                <div className="truncate text-slate-600">{progress.start_url}</div>
                <div className="text-slate-400 mt-0.5">
                  {progress.pages_visited}/{progress.max_pages} pages
                </div>
              </div>
            )}
            {session.run_ids.length === 0 && !progress && (
              <div className="text-xs text-slate-400 px-1">No crawl runs yet</div>
            )}
            {[...session.run_ids].reverse().map((id) =>
              runs[id] ? (
                <RunCard key={id} run={runs[id]} />
              ) : (
                <div
                  key={id}
                  className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-400"
                >
                  loading {id}…
                </div>
              ),
            )}
          </>
        )}
        {active === 'comparison' && session.comparison_result && (
          <ComparisonView comparison={session.comparison_result} sessionId={session.id} />
        )}
      </div>
    </aside>
  );
}

function TabButton({
  label,
  active,
  disabled,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-40
        ${active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
    >
      {label}
    </button>
  );
}

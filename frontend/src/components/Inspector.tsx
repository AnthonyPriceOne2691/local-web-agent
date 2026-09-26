import { useState } from 'react';

import { pagesRead, siteCount, siteName } from '../copy';
import type { CrawlProgress, RunRecord, SessionRecord } from '../types';

import ComparisonView from './ComparisonView';
import RunCard from './RunCard';

interface Props {
  session: SessionRecord | null;
  runs: Record<string, RunRecord>;
  progress: CrawlProgress | null;
}

/** Правая панель: что агент видел на каждом сайте и чем сайты отличаются.
 *  Раньше называлась «Runs / Comparison» — терминами кода. */
export default function Inspector({ session, runs, progress }: Props) {
  const [tab, setTab] = useState<'sites' | 'verdict'>('sites');
  if (!session) return null;

  const hasVerdict = session.comparison_result != null;
  const active = tab === 'verdict' && hasVerdict ? 'verdict' : 'sites';

  return (
    <aside className="glass-panel flex w-full min-w-0 flex-col overflow-hidden rounded-[var(--radius-glass)] xl:w-[26rem] xl:shrink-0 lg:w-80 lg:shrink-0">
      <div className="flex h-14 shrink-0 items-center gap-1.5 border-b border-[var(--glass-edge)] px-3">
        <Tab
          label={`Sites visited · ${session.run_ids.length}`}
          active={active === 'sites'}
          onClick={() => setTab('sites')}
        />
        <Tab
          label="What we found"
          active={active === 'verdict'}
          disabled={!hasVerdict}
          onClick={() => setTab('verdict')}
        />
      </div>

      <div className="scroll-slim flex-1 space-y-2.5 overflow-y-auto p-3">
        {active === 'sites' && <SitesVisited session={session} runs={runs} progress={progress} />}
        {active === 'verdict' && session.comparison_result && (
          <ComparisonView comparison={session.comparison_result} sessionId={session.id} />
        )}
      </div>
    </aside>
  );
}

/** Сайт, который агент читает сейчас, стоит первым; пройденные — от новых к старым. */
function SitesVisited({
  session,
  runs,
  progress,
}: {
  session: SessionRecord;
  runs: Record<string, RunRecord>;
  progress: CrawlProgress | null;
}) {
  const pending = progress != null && !session.run_ids.includes(progress.run_id);
  return (
    <>
      {pending && progress && (
        <div className="glass-quiet rounded-2xl px-3.5 py-3">
          <div className="flex items-center gap-2 text-[13px] font-medium">
            <span className="size-1.5 animate-pulse rounded-full bg-[var(--color-accent)]" />
            {siteName(progress.start_url)}
          </div>
          <p className="text-faint mt-1 text-[11.5px]">
            {pagesRead(progress.pages_visited, progress.max_pages)}
          </p>
        </div>
      )}
      {session.run_ids.length === 0 && !pending && (
        <p className="text-faint px-1 py-4 text-[12px]">
          Nothing visited yet. Sites show up here as the agent works through them.
        </p>
      )}
      {[...session.run_ids].reverse().map((id) =>
        runs[id] ? (
          <RunCard key={id} run={runs[id]} />
        ) : (
          <p key={id} className="glass-quiet rounded-2xl px-3.5 py-3 text-faint text-[12px]">
            Loading what the agent saw…
          </p>
        ),
      )}
      {session.run_ids.length > 1 && (
        <p className="text-faint px-1 pt-1 text-[11px]">
          {siteCount(session.run_ids.length)} in this chat
        </p>
      )}
    </>
  );
}

function Tab({
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
      aria-pressed={active}
      className={`focus-ring rounded-full px-3.5 py-1.5 text-[12px] font-medium transition disabled:opacity-40
        ${active ? 'glass text-ink' : 'text-soft glass-slot'} press`}
    >
      {label}
    </button>
  );
}

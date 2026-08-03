import { pagesRead, siteName } from '../copy';
import type { CrawlProgress } from '../types';

/** Что происходит прямо сейчас: имя сайта, сколько страниц прочитано, и где агент
 *  находится. Раньше здесь стояли сырые URL и `3/10 pages`. */
export default function ProgressCard({ progress }: { progress: CrawlProgress }) {
  const pct = Math.min(100, Math.round((progress.pages_visited / progress.max_pages) * 100));
  return (
    <div className="glass rise-in rounded-3xl px-4 py-3.5">
      <div className="flex items-baseline gap-2">
        <span className="text-[13px] font-medium">Reading {siteName(progress.start_url)}</span>
        <span className="text-faint ml-auto shrink-0 text-[11px] tabular-nums">
          {pagesRead(progress.pages_visited, progress.max_pages)}
        </span>
      </div>
      <div className="glass-quiet shimmer-bar mt-2.5 h-1.5 rounded-full">
        <div
          className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      {progress.current_url && (
        <p className="text-faint mt-2 truncate text-[11px]">On {progress.current_url}</p>
      )}
    </div>
  );
}

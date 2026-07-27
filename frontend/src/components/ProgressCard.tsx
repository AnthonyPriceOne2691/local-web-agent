import type { CrawlProgress } from '../types';

export function Spinner() {
  return (
    <span className="inline-block size-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
  );
}

export default function ProgressCard({ progress }: { progress: CrawlProgress }) {
  const pct = Math.min(100, Math.round((progress.pages_visited / progress.max_pages) * 100));
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
      <div className="flex items-center gap-2 mb-1.5">
        <Spinner />
        <span className="font-medium truncate">Crawling {progress.start_url}</span>
        <span className="ml-auto tabular-nums">
          {progress.pages_visited}/{progress.max_pages} pages
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-blue-100 overflow-hidden">
        <div className="h-full bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      {progress.current_url && (
        <div className="mt-1 truncate text-blue-600">{progress.current_url}</div>
      )}
    </div>
  );
}

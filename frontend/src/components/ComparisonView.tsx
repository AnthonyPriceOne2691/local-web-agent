import { useState } from 'react';

import { api, downloadReport } from '../api';
import type { ComparisonResult } from '../types';

export default function ComparisonView({
  comparison,
  sessionId,
}: {
  comparison: ComparisonResult;
  sessionId: string;
}) {
  const [error, setError] = useState('');
  const siteColumns = [...new Set(comparison.dimensions.flatMap((d) => Object.keys(d.scores)))];

  return (
    <div className="space-y-3 text-xs">
      <div className="flex gap-2">
        <button
          onClick={() => downloadReport(sessionId).catch((e) => setError(String(e)))}
          className="rounded-md bg-slate-900 text-white px-3 py-1.5 font-medium hover:bg-slate-700"
        >
          ⬇ Export report.md
        </button>
        <a
          href={api.reportUrl(sessionId)}
          target="_blank"
          rel="noreferrer"
          className="rounded-md border border-slate-300 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-100"
        >
          Open raw
        </a>
      </div>
      {error && <div className="text-red-600">{error}</div>}

      {comparison.winner && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
          <div className="font-semibold text-emerald-800">
            🏆 {comparison.winner.label || comparison.winner.start_url}
          </div>
          <div className="mt-1 text-emerald-700">{comparison.winner.reason}</div>
        </div>
      )}

      {comparison.rankings.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 space-y-2">
          <div className="font-semibold text-slate-700">Rankings</div>
          {comparison.rankings.map((r) => (
            <div key={r.url}>
              <div className="flex justify-between gap-2">
                <span className="truncate text-slate-600">{r.url}</span>
                <span className="font-semibold tabular-nums">{r.score}</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full bg-blue-500"
                  style={{ width: `${Math.min(100, Math.max(0, r.score))}%` }}
                />
              </div>
              {r.summary && <div className="mt-0.5 text-slate-400 line-clamp-2">{r.summary}</div>}
            </div>
          ))}
        </div>
      )}

      {comparison.dimensions.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 overflow-x-auto">
          <div className="font-semibold text-slate-700 mb-2">
            Dimensions <span className="font-normal text-slate-400">· {comparison.rubric}</span>
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="pr-2 pb-1 font-medium">dimension</th>
                {siteColumns.map((site) => (
                  <th key={site} className="px-2 pb-1 font-medium max-w-28 truncate" title={site}>
                    {site}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparison.dimensions.map((d) => (
                <tr key={d.name} className="border-t border-slate-100 align-top">
                  <td className="pr-2 py-1.5 font-medium text-slate-600">{d.name}</td>
                  {siteColumns.map((site) => (
                    <td key={site} className="px-2 py-1.5 text-slate-500">
                      {String(d.scores[site] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {comparison.narrative && (
        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="font-semibold text-slate-700 mb-1">Narrative</div>
          <div className="whitespace-pre-wrap text-slate-600">{comparison.narrative}</div>
        </div>
      )}

      {comparison.excluded.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <div className="font-semibold text-amber-800 mb-1">Excluded sites</div>
          {comparison.excluded.map((e) => (
            <div key={e.start_url} className="text-amber-700">
              {e.start_url} — {e.reason}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

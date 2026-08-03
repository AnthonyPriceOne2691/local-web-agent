import { useState } from 'react';

import { downloadReport } from '../api';
import { errorText, humanizeKey, rubricLabel, siteName } from '../copy';
import type { ComparisonResult } from '../types';

/** Сравнение сайтов человеческим языком: «Best of the bunch» вместо `winner`,
 *  «Side by side» вместо `dimensions`, «In short» вместо `narrative`. */
export default function ComparisonView({
  comparison,
  sessionId,
}: {
  comparison: ComparisonResult;
  sessionId: string;
}) {
  const [error, setError] = useState('');
  const columns = [...new Set(comparison.dimensions.flatMap((d) => Object.keys(d.scores)))];

  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <button
          onClick={() => downloadReport(sessionId).catch((e) => setError(errorText(e)))}
          className="btn-accent focus-ring rounded-full px-3.5 py-1.5 text-[12px] font-medium"
        >
          Save as a document
        </button>
        <span className="text-faint text-[11px]">Compared on {rubricLabel(comparison.rubric)}</span>
      </div>
      {error && <p className="text-[12px] text-[var(--color-rose-warm)]">{error}</p>}

      {comparison.winner && (
        <section className="glass rounded-2xl px-3.5 py-3">
          <h3 className="text-[11px] font-medium tracking-wide text-[var(--color-mint)] uppercase">
            Best of the bunch
          </h3>
          <p className="mt-1 text-[14px] font-semibold">
            {comparison.winner.label || siteName(comparison.winner.start_url)}
          </p>
          <p className="text-soft mt-1 text-[12.5px] leading-relaxed">{comparison.winner.reason}</p>
        </section>
      )}

      {comparison.rankings.length > 0 && (
        <section className="glass-quiet space-y-2.5 rounded-2xl px-3.5 py-3">
          <h3 className="text-faint text-[11px] font-medium tracking-wide uppercase">
            How they scored
          </h3>
          {comparison.rankings.map((r) => (
            <div key={r.url}>
              <div className="flex items-baseline justify-between gap-2 text-[12.5px]">
                <span className="truncate font-medium">{siteName(r.url)}</span>
                <span className="shrink-0 tabular-nums">{r.score} / 100</span>
              </div>
              <div className="glass-quiet mt-1 h-1.5 rounded-full">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${Math.min(100, Math.max(0, r.score))}%` }}
                />
              </div>
              {r.summary && (
                <p className="text-faint mt-1 line-clamp-2 text-[11.5px] leading-relaxed">
                  {r.summary}
                </p>
              )}
            </div>
          ))}
        </section>
      )}

      {comparison.dimensions.length > 0 && (
        <section className="glass-quiet rounded-2xl px-3.5 py-3">
          <h3 className="text-faint mb-2 text-[11px] font-medium tracking-wide uppercase">
            Side by side
          </h3>
          {/* Оценки — числа, и колонка чисел читается только выровненной по центру
              под своим заголовком: слева они разъезжались и глазом не сравнивались.
              Первая колонка (название размерности) остаётся по левому краю — это текст. */}
          <div className="scroll-slim overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-faint">
                  <th className="pr-3 pb-1.5 text-left font-medium">What we looked at</th>
                  {columns.map((site) => (
                    <th
                      key={site}
                      className="max-w-24 truncate px-2 pb-1.5 text-center font-medium"
                      title={site}
                    >
                      {siteName(site)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.dimensions.map((d) => (
                  <tr key={d.name} className="border-t border-[var(--glass-edge)] align-top">
                    <td className="text-soft py-1.5 pr-3">{humanizeKey(d.name)}</td>
                    {columns.map((site) => (
                      <td key={site} className="text-soft px-2 py-1.5 text-center tabular-nums">
                        {String(d.scores[site] ?? '—')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {comparison.narrative && (
        <section className="glass-quiet rounded-2xl px-3.5 py-3">
          <h3 className="text-faint mb-1.5 text-[11px] font-medium tracking-wide uppercase">
            In short
          </h3>
          <p className="text-soft text-[12.5px] leading-relaxed whitespace-pre-wrap">
            {comparison.narrative}
          </p>
        </section>
      )}

      {comparison.excluded.length > 0 && (
        <section className="glass-quiet rounded-2xl px-3.5 py-3">
          <h3 className="mb-1.5 text-[11px] font-medium tracking-wide text-[var(--color-amber-warm)] uppercase">
            Left out
          </h3>
          {comparison.excluded.map((e) => (
            <p key={e.start_url} className="text-soft text-[12px] leading-relaxed">
              <span className="font-medium">{siteName(e.start_url)}</span> — {e.reason}
            </p>
          ))}
        </section>
      )}
    </div>
  );
}

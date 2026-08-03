import { useState } from 'react';

import { relativeTime, sessionState, siteCount } from '../copy';
import type { SessionListItem } from '../types';

import StatusPill from './StatusPill';

interface Props {
  sessions: SessionListItem[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export default function Sidebar({ sessions, currentId, onSelect, onNew, onDelete }: Props) {
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <aside className="glass-panel flex w-64 shrink-0 flex-col overflow-hidden rounded-[var(--radius-glass)]">
      <div className="flex items-start gap-2 px-4 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-[15px] font-semibold tracking-tight">Local Web Agent</div>
          <div className="text-faint mt-0.5 text-[11px]">Research that never leaves this Mac</div>
        </div>
        {/* Плюс рисуется фигурой, а не глифом «+»: у глифа своя метрика и оптический
            центр не совпадает с центром круга — кнопка выглядела съехавшей. */}
        <button
          onClick={onNew}
          aria-label="Start a new chat"
          className="btn-accent focus-ring press grid size-8 shrink-0 place-items-center rounded-full"
        >
          <svg viewBox="0 0 16 16" aria-hidden className="size-4">
            <path
              d="M8 3.25v9.5M3.25 8h9.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      {/* Промежуток между карточками задаётся списком (`gap`), а не отступами у
          каждой карточки: иначе он то удваивается, то исчезает при вставке блока
          подтверждения удаления. Карточки стояли вплотную и читались как одна. */}
      <nav className="scroll-slim flex flex-1 flex-col gap-1.5 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 && (
          <p className="text-faint px-2 py-6 text-center text-xs">
            No chats yet. Paste a few links and ask a question.
          </p>
        )}
        {sessions.map((s) => {
          const state = sessionState(s.status);
          const selected = s.session_id === currentId;
          return (
            <div key={s.session_id} className="group relative">
              <button
                onClick={() => onSelect(s.session_id)}
                aria-current={selected ? 'true' : undefined}
                className={`focus-ring press block w-full rounded-2xl px-3 py-2.5 text-left
                  ${selected ? 'glass' : 'glass-slot'}`}
              >
                <span className="block truncate pr-6 text-[13px] font-medium">
                  {s.title || 'Untitled chat'}
                </span>
                <span className="mt-1.5 flex items-center gap-2">
                  <StatusPill label={state.text} tone={state.tone} live={state.tone === 'busy'} />
                  <span className="text-faint truncate text-[11px]">
                    {siteCount(s.runs)} · {relativeTime(s.created_at)}
                  </span>
                </span>
              </button>
              <button
                onClick={() => setConfirming(s.session_id)}
                aria-label={`Delete chat ${s.title || 'Untitled chat'}`}
                className="text-faint focus-ring absolute top-2.5 right-2 rounded-full px-1.5 py-0.5 text-xs opacity-0 transition group-hover:opacity-100 hover:text-[var(--color-rose-warm)]"
              >
                ✕
              </button>
              {confirming === s.session_id && (
                <ConfirmDelete
                  onCancel={() => setConfirming(null)}
                  onConfirm={() => {
                    setConfirming(null);
                    onDelete(s.session_id);
                  }}
                />
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

/** Подтверждение живёт в интерфейсе, а не в системном `confirm()`: тот блокирует
 *  поток, выглядит чужеродно и не стилизуется. */
function ConfirmDelete({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  return (
    <div className="glass mx-1 mt-1 rounded-2xl px-3 py-2.5">
      <p className="text-[12px]">Delete this chat and everything it found?</p>
      <div className="mt-2 flex gap-1.5">
        <button
          onClick={onConfirm}
          className="focus-ring rounded-full bg-[var(--color-rose-warm)] px-3 py-1 text-[11px] font-medium text-white"
        >
          Delete
        </button>
        <button
          onClick={onCancel}
          className="glass-quiet focus-ring text-soft rounded-full px-3 py-1 text-[11px] font-medium"
        >
          Keep it
        </button>
      </div>
    </div>
  );
}

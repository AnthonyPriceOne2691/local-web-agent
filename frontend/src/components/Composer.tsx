import { useState } from 'react';

interface Props {
  busy: boolean;
  sending: boolean;
  attended: boolean;
  hasSession: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: (content: string) => void;
  onToggleAttended: (value: boolean) => void;
}

/** Ввод сообщения + тумблер attended. Черновик живёт выше (Chat), чтобы кнопки
 *  примеров из welcome-экрана могли его заполнить. */
export default function Composer({
  busy,
  sending,
  attended,
  hasSession,
  draft,
  onDraftChange,
  onSend,
  onToggleAttended,
}: Props) {
  const [rows, setRows] = useState(1);

  const submit = () => {
    const text = draft.trim();
    if (!text || sending || busy) return;
    onSend(text);
  };

  const update = (value: string) => {
    onDraftChange(value);
    setRows(Math.min(6, Math.max(1, value.split('\n').length)));
  };

  return (
    <footer className="shrink-0 border-t border-slate-200 bg-white p-3">
      <div className="flex gap-2 items-end">
        <textarea
          value={draft}
          onChange={(e) => update(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={rows}
          placeholder={
            busy ? 'Session is running — wait or cancel…' : 'URLs + task… (Enter to send)'
          }
          disabled={busy}
          className="flex-1 resize-none rounded-lg border border-slate-300 focus:border-blue-500 focus:outline-none px-3 py-2 text-sm disabled:bg-slate-50"
        />
        <button
          onClick={submit}
          disabled={busy || sending || !draft.trim()}
          className="rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-300 text-white px-4 py-2 text-sm font-medium"
        >
          Send
        </button>
      </div>
      <label
        className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-500 select-none w-fit"
        title="Видимый браузер: на anti-bot проверке пауза — пройди её сам, дальше агент продолжит"
      >
        <input
          type="checkbox"
          checked={attended}
          disabled={hasSession || busy}
          onChange={(e) => onToggleAttended(e.target.checked)}
          className="accent-blue-600"
        />
        Attended-режим (пройти проверки вручную) — задаётся при старте новой сессии
      </label>
    </footer>
  );
}

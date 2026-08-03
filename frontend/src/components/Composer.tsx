import { useState } from 'react';

interface Props {
  busy: boolean;
  sending: boolean;
  watchBrowser: boolean;
  hasSession: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: (content: string) => void;
  onToggleWatchBrowser: (value: boolean) => void;
}

/** Ввод сообщения. Черновик живёт выше (Chat), чтобы примеры с приветственного
 *  экрана могли его заполнить. */
export default function Composer({
  busy,
  sending,
  watchBrowser,
  hasSession,
  draft,
  onDraftChange,
  onSend,
  onToggleWatchBrowser,
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

  // Подсказка в поле ввода. На узком окне длинная фраза обрезалась на середине слова
  // («The agent is working — / wait for it, or press Stop»), и текст читался как
  // сломанный. Placeholder укоротить нельзя условно — CSS его не измеряет, — поэтому
  // подсказку про Enter/Shift+Enter выносим ПОД поле, а в placeholder оставляем
  // короткую фразу, которая влезает в одну строку на любой ширине.
  const placeholder = busy ? 'Working — or press Stop' : 'Paste links and say what you need';

  return (
    <footer className="shrink-0 border-t border-[var(--glass-edge)] px-4 py-3.5 sm:px-5 sm:py-4">
      <div className="flex items-end gap-2">
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
          aria-label="Your links and question"
          placeholder={placeholder}
          disabled={busy}
          className="glass-quiet focus-ring text-ink placeholder:text-faint min-w-0 flex-1 resize-none rounded-2xl px-4 py-3 text-[14px] outline-none disabled:opacity-60"
        />
        <button
          onClick={submit}
          disabled={busy || sending || !draft.trim()}
          aria-label={sending ? 'Sending' : 'Send'}
          className="btn-accent focus-ring press shrink-0 rounded-2xl px-4 py-3 text-[14px] font-medium sm:px-5"
        >
          {sending ? 'Sending…' : 'Send'}
        </button>
      </div>

      {/* Две подсказки в одну строку, каждая отдельным элементом: тогда перенос
          проходит между ними, а не разрывает фразу пополам. */}
      <div className="text-faint mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px]">
        {!busy && <span className="shrink-0">Enter sends · Shift+Enter adds a line</span>}
        <label className="flex min-w-0 cursor-pointer items-start gap-2 select-none">
          <input
            type="checkbox"
            checked={watchBrowser}
            disabled={hasSession || busy}
            onChange={(e) => onToggleWatchBrowser(e.target.checked)}
            className="focus-ring mt-0.5 size-3.5 shrink-0 accent-[var(--color-accent)]"
          />
          <span className="min-w-0">
            Show me the browser — I&apos;ll handle logins and “are you a robot” checks myself
            {hasSession && ' (pick this before the first message)'}
          </span>
        </label>
      </div>
    </footer>
  );
}

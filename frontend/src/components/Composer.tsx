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

  return (
    <footer className="shrink-0 border-t border-[var(--glass-edge)] px-5 py-4">
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
          placeholder={
            busy
              ? 'The agent is working — wait for it, or press Stop'
              : 'Paste links and say what you need. Enter sends, Shift+Enter adds a line.'
          }
          disabled={busy}
          className="glass-quiet focus-ring text-ink placeholder:text-faint flex-1 resize-none rounded-2xl px-4 py-3 text-[14px] outline-none disabled:opacity-60"
        />
        <button
          onClick={submit}
          disabled={busy || sending || !draft.trim()}
          className="btn-accent focus-ring rounded-2xl px-5 py-3 text-[14px] font-medium"
        >
          {sending ? 'Sending…' : 'Send'}
        </button>
      </div>

      <label className="text-faint mt-2.5 flex w-fit cursor-pointer items-center gap-2 text-[11px] select-none">
        <input
          type="checkbox"
          checked={watchBrowser}
          disabled={hasSession || busy}
          onChange={(e) => onToggleWatchBrowser(e.target.checked)}
          className="focus-ring size-3.5 accent-[var(--color-accent)]"
        />
        <span>
          Show me the browser — I&apos;ll handle logins and “are you a robot” checks myself
          {hasSession && ' (pick this before the first message)'}
        </span>
      </label>
    </footer>
  );
}

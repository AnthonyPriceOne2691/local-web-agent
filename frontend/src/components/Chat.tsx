import { useEffect, useRef, useState } from 'react';

import { sessionState } from '../copy';
import type { ChallengeWait, CrawlProgress, SessionRecord } from '../types';

import ChallengeCard from './ChallengeCard';
import Composer from './Composer';
import Message from './Message';
import ProgressCard from './ProgressCard';
import StatusPill from './StatusPill';
import WelcomeScreen from './WelcomeScreen';

interface Props {
  session: SessionRecord | null;
  progress: CrawlProgress | null;
  challenge: ChallengeWait | null;
  error: string;
  sending: boolean;
  busy: boolean;
  watchBrowser: boolean;
  onSend: (content: string) => void;
  onStop: () => void;
  onResume: () => void;
  onDismissError: () => void;
  onToggleWatchBrowser: (value: boolean) => void;
}

export default function Chat({
  session,
  progress,
  challenge,
  error,
  sending,
  busy,
  watchBrowser,
  onSend,
  onStop,
  onResume,
  onDismissError,
  onToggleWatchBrowser,
}: Props) {
  const [draft, setDraft] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.messages.length, progress?.pages_visited, challenge]);

  return (
    <main className="glass-panel flex min-w-0 flex-1 flex-col overflow-hidden rounded-[var(--radius-glass)]">
      <ChatHeader session={session} busy={busy} onStop={onStop} />

      <div className="scroll-slim flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-5">
        {!session && <WelcomeScreen onPick={setDraft} />}
        <ChatFeed session={session} progress={progress} challenge={challenge} onResume={onResume} />
        <div ref={bottomRef} />
      </div>

      {error && <ErrorNotice error={error} onDismiss={onDismissError} />}

      <Composer
        busy={busy}
        sending={sending}
        watchBrowser={watchBrowser}
        hasSession={session != null}
        draft={draft}
        onDraftChange={setDraft}
        onSend={(text) => {
          setDraft('');
          onSend(text);
        }}
        onToggleWatchBrowser={onToggleWatchBrowser}
      />
    </main>
  );
}

function ChatHeader({
  session,
  busy,
  onStop,
}: {
  session: SessionRecord | null;
  busy: boolean;
  onStop: () => void;
}) {
  const state = session ? sessionState(session.status) : null;
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--glass-edge)] px-5">
      <h1 className="min-w-0 flex-1 truncate text-[15px] font-semibold tracking-tight">
        {session ? session.title || 'Untitled chat' : 'New research chat'}
      </h1>
      {state && <StatusPill label={state.text} tone={state.tone} live={state.tone === 'busy'} />}
      {busy && (
        <button
          onClick={onStop}
          className="glass-quiet glass-hover focus-ring rounded-full px-3 py-1.5 text-xs font-medium text-[var(--color-rose-warm)]"
        >
          Stop
        </button>
      )}
    </header>
  );
}

/** Реплики, а под ними — что агент делает прямо сейчас: ждёт человека на проверке,
 *  читает сайт или сравнивает найденное. */
function ChatFeed({
  session,
  progress,
  challenge,
  onResume,
}: {
  session: SessionRecord | null;
  progress: CrawlProgress | null;
  challenge: ChallengeWait | null;
  onResume: () => void;
}) {
  return (
    <>
      {session?.messages.map((m, i) => (
        <Message key={i} message={m} />
      ))}
      {challenge && <ChallengeCard challenge={challenge} onResume={onResume} />}
      {progress && !challenge && <ProgressCard progress={progress} />}
      {session?.status === 'comparing' && (
        <p className="text-soft flex items-center gap-2 px-1 text-[13px]">
          <span className="size-1.5 animate-pulse rounded-full bg-[var(--color-accent)]" />
          Weighing the sites against each other…
        </p>
      )}
    </>
  );
}

function ErrorNotice({ error, onDismiss }: { error: string; onDismiss: () => void }) {
  return (
    <div className="glass mx-5 mb-3 flex items-start gap-3 rounded-2xl px-4 py-3">
      <span aria-hidden className="text-[var(--color-rose-warm)]">
        ⚠
      </span>
      <p className="flex-1 text-[13px]">{error}</p>
      <button
        onClick={onDismiss}
        aria-label="Dismiss this message"
        className="text-faint focus-ring rounded-full px-1 text-xs"
      >
        ✕
      </button>
    </div>
  );
}

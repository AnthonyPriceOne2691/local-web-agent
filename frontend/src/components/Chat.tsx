import { useEffect, useRef, useState } from 'react';

import type { ChallengeWait, CrawlProgress, SessionRecord } from '../types';

import ChallengeCard from './ChallengeCard';
import Composer from './Composer';
import Message from './Message';
import ProgressCard, { Spinner } from './ProgressCard';
import StatusBadge from './StatusBadge';
import WelcomeScreen from './WelcomeScreen';

interface Props {
  session: SessionRecord | null;
  progress: CrawlProgress | null;
  challenge: ChallengeWait | null;
  banner: string;
  sending: boolean;
  attended: boolean;
  onSend: (content: string) => void;
  onCancel: () => void;
  onResume: () => void;
  onToggleAttended: (value: boolean) => void;
}

export default function Chat({
  session,
  progress,
  challenge,
  banner,
  sending,
  attended,
  onSend,
  onCancel,
  onResume,
  onToggleAttended,
}: Props) {
  const [draft, setDraft] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = session != null && ['running_tools', 'comparing'].includes(session.status);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.messages.length, progress?.pages_visited, challenge]);

  const send = (content: string) => {
    setDraft('');
    onSend(content);
  };

  return (
    <main className="flex-1 flex flex-col min-w-0">
      <header className="h-12 shrink-0 bg-white border-b border-slate-200 flex items-center gap-3 px-4">
        <h1 className="flex-1 truncate text-sm font-semibold">
          {session ? session.title || 'Untitled session' : 'New research chat'}
        </h1>
        {session && <StatusBadge status={session.status} />}
        {busy && (
          <button
            onClick={onCancel}
            className="rounded-md border border-red-300 text-red-600 hover:bg-red-50 px-2.5 py-1 text-xs font-medium"
          >
            Cancel
          </button>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {!session && <WelcomeScreen onPick={setDraft} />}
        {session?.messages.map((m, i) => (
          <Message key={i} message={m} />
        ))}
        {challenge && <ChallengeCard challenge={challenge} onResume={onResume} />}
        {progress && !challenge && <ProgressCard progress={progress} />}
        {session?.status === 'comparing' && (
          <div className="flex items-center gap-2 text-sm text-violet-600">
            <Spinner /> Comparing results…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {banner && (
        <div className="mx-4 mb-2 rounded-md bg-red-50 border border-red-200 text-red-700 text-xs px-3 py-2">
          {banner}
        </div>
      )}

      <Composer
        busy={busy}
        sending={sending}
        attended={attended}
        hasSession={session != null}
        draft={draft}
        onDraftChange={setDraft}
        onSend={send}
        onToggleAttended={onToggleAttended}
      />
    </main>
  );
}

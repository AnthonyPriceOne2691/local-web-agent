import { useCallback, useEffect, useRef, useState } from 'react';
import { api, subscribeSessionEvents } from './api';
import Chat from './components/Chat';
import Sidebar from './components/Sidebar';
import SidePanel from './components/SidePanel';
import type {
  ChallengeWait,
  CrawlProgress,
  RunRecord,
  SessionListItem,
  SessionRecord,
} from './types';

const BUSY: string[] = ['running_tools', 'comparing'];

export default function App() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [current, setCurrent] = useState<SessionRecord | null>(null);
  const [progress, setProgress] = useState<CrawlProgress | null>(null);
  const [challenge, setChallenge] = useState<ChallengeWait | null>(null);
  const [attended, setAttended] = useState(false);
  const [runs, setRuns] = useState<Record<string, RunRecord>>({});
  const [banner, setBanner] = useState('');
  const [sending, setSending] = useState(false);
  const unsubRef = useRef<(() => void) | null>(null);

  const detach = () => {
    unsubRef.current?.();
    unsubRef.current = null;
  };

  const refreshSessions = useCallback(() => {
    api
      .listSessions()
      .then((d) => setSessions(d.sessions))
      .catch((e) => setBanner(String(e)));
  }, []);

  useEffect(() => {
    refreshSessions();
    return detach;
  }, [refreshSessions]);

  const fetchRuns = useCallback((ids: string[]) => {
    for (const id of ids) {
      api
        .getRun(id)
        .then((r) => setRuns((prev) => ({ ...prev, [r.id]: r })))
        .catch((e: unknown) => console.error(`getRun ${id} failed`, e));
    }
  }, []);

  /** Подписка на SSE активной сессии; события мутируют current инкрементально,
   * done — рефетч полного состояния (источник правды — GET /sessions/{id}). */
  const attach = useCallback(
    (sessionId: string, sinceMessages: number) => {
      detach();
      unsubRef.current = subscribeSessionEvents(sessionId, sinceMessages, {
        onMessage: (m) =>
          setCurrent((prev) => {
            if (!prev || prev.id !== sessionId || m.index < prev.messages.length) return prev;
            if (m.role === 'tool') {
              // новый tool-вызов → подтянуть завершившиеся runs сессии
              api
                .getSession(sessionId)
                .then((full) => {
                  setCurrent((p) =>
                    p && p.id === sessionId ? { ...p, run_ids: full.run_ids } : p,
                  );
                  fetchRuns(full.run_ids);
                })
                .catch((e: unknown) => console.error('getSession after tool-note failed', e));
            }
            const msg = { role: m.role, content: m.content, created_at: m.created_at };
            return { ...prev, messages: [...prev.messages, msg] };
          }),
        onStatus: (status) =>
          setCurrent((prev) =>
            prev && prev.id === sessionId
              ? { ...prev, status: status as SessionRecord['status'] }
              : prev,
          ),
        onProgress: (p) => {
          setProgress(p);
          if (p.status !== 'waiting_user') setChallenge(null); // прошли — снять карточку
        },
        onChallenge: (c) => setChallenge(c),
        onDone: () => {
          detach();
          setProgress(null);
          setChallenge(null);
          api
            .getSession(sessionId)
            .then((full) => {
              setCurrent((prev) => (prev && prev.id === sessionId ? full : prev));
              fetchRuns(full.run_ids);
            })
            .catch((e: unknown) => console.error('getSession on done failed', e));
          refreshSessions();
        },
      });
    },
    [fetchRuns, refreshSessions],
  );

  const selectSession = (id: string) => {
    detach();
    setProgress(null);
    setChallenge(null);
    setBanner('');
    api
      .getSession(id)
      .then((sess) => {
        setCurrent(sess);
        fetchRuns(sess.run_ids);
        if (BUSY.includes(sess.status)) attach(sess.id, sess.messages.length);
      })
      .catch((e) => setBanner(String(e)));
  };

  const newChat = () => {
    detach();
    setCurrent(null);
    setProgress(null);
    setChallenge(null);
    setBanner('');
  };

  const send = async (content: string) => {
    setSending(true);
    setBanner('');
    try {
      let sess = current;
      if (!sess) {
        const { session_id } = await api.createSession('', attended);
        sess = await api.getSession(session_id);
        setCurrent(sess);
        refreshSessions();
      }
      const since = sess.messages.length;
      await api.postMessage(sess.id, content);
      setCurrent((prev) => (prev ? { ...prev, status: 'running_tools' } : prev));
      attach(sess.id, since); // user message придёт первым SSE-событием
    } catch (e) {
      setBanner(String(e));
    } finally {
      setSending(false);
    }
  };

  const cancel = () => {
    if (current) api.cancelSession(current.id).catch((e) => setBanner(String(e)));
  };

  const resume = () => {
    if (!current) return;
    setChallenge(null); // оптимистично; SSE подтвердит прогрессом
    api.resumeSession(current.id).catch((e) => setBanner(String(e)));
  };

  const removeSession = (id: string) => {
    api
      .deleteSession(id)
      .then(() => {
        if (current?.id === id) newChat();
        refreshSessions();
      })
      .catch((e) => setBanner(String(e)));
  };

  return (
    <div className="h-screen flex bg-slate-100 text-slate-900">
      <Sidebar
        sessions={sessions}
        currentId={current?.id ?? null}
        onSelect={selectSession}
        onNew={newChat}
        onDelete={removeSession}
      />
      <Chat
        session={current}
        progress={progress}
        challenge={challenge}
        banner={banner}
        sending={sending}
        attended={attended}
        onSend={send}
        onCancel={cancel}
        onResume={resume}
        onToggleAttended={setAttended}
      />
      <SidePanel session={current} runs={runs} progress={progress} />
    </div>
  );
}

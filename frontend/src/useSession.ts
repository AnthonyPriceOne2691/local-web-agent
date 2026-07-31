import { useCallback, useEffect, useState } from 'react';

import { api } from './api';
import { errorText } from './copy';
import type {
  ChallengeWait,
  CrawlProgress,
  RunRecord,
  SessionListItem,
  SessionRecord,
} from './types';
import { type SessionStream, useSessionStream } from './useSessionStream';

const BUSY: string[] = ['running_tools', 'comparing'];

export interface SessionActions {
  select: (id: string) => void;
  startNew: () => void;
  send: (content: string) => Promise<void>;
  stop: () => void;
  resume: () => void;
  remove: (id: string) => void;
}

export interface SessionController extends SessionActions {
  sessions: SessionListItem[];
  current: SessionRecord | null;
  runs: Record<string, RunRecord>;
  progress: CrawlProgress | null;
  challenge: ChallengeWait | null;
  error: string;
  sending: boolean;
  watchBrowser: boolean;
  busy: boolean;
  setWatchBrowser: (value: boolean) => void;
  dismissError: () => void;
}

interface Deps {
  current: SessionRecord | null;
  watchBrowser: boolean;
  stream: SessionStream;
  refreshSessions: () => void;
  setCurrent: React.Dispatch<React.SetStateAction<SessionRecord | null>>;
  setProgress: (p: CrawlProgress | null) => void;
  setChallenge: (c: ChallengeWait | null) => void;
  setSending: (value: boolean) => void;
  setError: (message: string) => void;
}

/** Действия пользователя. Вынесены из тела хука: иначе один файл смешивает
 *  «что храним» и «что делаем», и любая правка требует читать оба. */
function makeActions(d: Deps): SessionActions {
  const fail = (e: unknown) => d.setError(errorText(e));

  const clearView = () => {
    d.stream.detach();
    d.setProgress(null);
    d.setChallenge(null);
    d.setError('');
  };

  const startNew = () => {
    clearView();
    d.setCurrent(null);
  };

  const send = async (content: string) => {
    d.setSending(true);
    d.setError('');
    try {
      let sess = d.current;
      if (!sess) {
        const { session_id } = await api.createSession('', d.watchBrowser);
        sess = await api.getSession(session_id);
        d.setCurrent(sess);
        d.refreshSessions();
      }
      const since = sess.messages.length;
      await api.postMessage(sess.id, content);
      d.setCurrent((prev) => (prev ? { ...prev, status: 'running_tools' } : prev));
      d.stream.attach(sess.id, since); // сообщение пользователя вернётся первым событием
    } catch (e) {
      fail(e);
    } finally {
      d.setSending(false);
    }
  };

  return {
    startNew,
    send,
    select: (id) => {
      clearView();
      api
        .getSession(id)
        .then((sess) => {
          d.setCurrent(sess);
          d.stream.loadSites(sess.run_ids);
          if (BUSY.includes(sess.status)) d.stream.attach(sess.id, sess.messages.length);
        })
        .catch(fail);
    },
    stop: () => {
      if (d.current) api.cancelSession(d.current.id).catch(fail);
    },
    resume: () => {
      if (!d.current) return;
      d.setChallenge(null); // оптимистично: прогресс подтвердит
      api.resumeSession(d.current.id).catch(fail);
    },
    remove: (id) => {
      api
        .deleteSession(id)
        .then(() => {
          if (d.current?.id === id) startNew();
          d.refreshSessions();
        })
        .catch(fail);
    },
  };
}

/** Состояние чата. Подписка — в `useSessionStream`, действия — в `makeActions`. */
export function useSession(): SessionController {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [current, setCurrent] = useState<SessionRecord | null>(null);
  const [runs, setRuns] = useState<Record<string, RunRecord>>({});
  const [progress, setProgress] = useState<CrawlProgress | null>(null);
  const [challenge, setChallenge] = useState<ChallengeWait | null>(null);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [watchBrowser, setWatchBrowser] = useState(false);

  const refreshSessions = useCallback(() => {
    api
      .listSessions()
      .then((d) => setSessions(d.sessions))
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  const stream = useSessionStream({
    setCurrent,
    setProgress,
    setChallenge,
    setRuns,
    onFinished: refreshSessions,
  });

  useEffect(() => {
    refreshSessions();
    return stream.detach;
  }, [refreshSessions, stream.detach]);

  const actions = makeActions({
    current,
    watchBrowser,
    stream,
    refreshSessions,
    setCurrent,
    setProgress,
    setChallenge,
    setSending,
    setError,
  });

  return {
    ...actions,
    sessions,
    current,
    runs,
    progress,
    challenge,
    error,
    sending,
    watchBrowser,
    busy: current != null && BUSY.includes(current.status),
    setWatchBrowser,
    dismissError: () => setError(''),
  };
}

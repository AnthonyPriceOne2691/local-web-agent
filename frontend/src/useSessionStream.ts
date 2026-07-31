import { useCallback, useRef } from 'react';

import { api, subscribeSessionEvents } from './api';
import type { ChallengeWait, CrawlProgress, RunRecord, SessionRecord } from './types';

interface Sinks {
  setCurrent: React.Dispatch<React.SetStateAction<SessionRecord | null>>;
  setProgress: (p: CrawlProgress | null) => void;
  setChallenge: (c: ChallengeWait | null) => void;
  setRuns: React.Dispatch<React.SetStateAction<Record<string, RunRecord>>>;
  onFinished: () => void;
}

export interface SessionStream {
  attach: (sessionId: string, sinceMessages: number) => void;
  detach: () => void;
  loadSites: (ids: string[]) => void;
}

/**
 * Живая подписка на события сессии.
 *
 * Отдельно от `useSession` не по вкусу: подписка — единственная часть, где есть
 * ресурс с временем жизни (EventSource) и порядок событий. Держать её рядом с
 * обработчиками кнопок значит каждый раз перечитывать одно, чтобы поправить другое.
 */
export function useSessionStream(sinks: Sinks): SessionStream {
  const unsubRef = useRef<(() => void) | null>(null);
  const sinksRef = useRef(sinks);
  sinksRef.current = sinks; // хендлеры всегда свежие, а подписка не пересоздаётся

  const detach = useCallback(() => {
    unsubRef.current?.();
    unsubRef.current = null;
  }, []);

  const loadSites = useCallback((ids: string[]) => {
    for (const id of ids) {
      api
        .getRun(id)
        .then((r) => sinksRef.current.setRuns((prev) => ({ ...prev, [r.id]: r })))
        .catch((e: unknown) => console.error(`loading site ${id} failed`, e));
    }
  }, []);

  /** `replace` — перечитать сессию целиком (источник правды GET /sessions/{id});
   *  иначе подтянуть только список сайтов, не трогая уже показанные сообщения. */
  const reload = useCallback(
    (sessionId: string, replace: boolean) => {
      api
        .getSession(sessionId)
        .then((full) => {
          sinksRef.current.setCurrent((prev) => {
            if (!prev || prev.id !== sessionId) return prev;
            return replace ? full : { ...prev, run_ids: full.run_ids };
          });
          loadSites(full.run_ids);
        })
        .catch((e: unknown) => console.error('refreshing the chat failed', e));
    },
    [loadSites],
  );

  const attach = useCallback(
    (sessionId: string, sinceMessages: number) => {
      detach();
      unsubRef.current = subscribeSessionEvents(sessionId, sinceMessages, {
        onMessage: (m) =>
          sinksRef.current.setCurrent((prev) => {
            if (!prev || prev.id !== sessionId || m.index < prev.messages.length) return prev;
            if (m.role === 'tool') reload(sessionId, false); // новый шаг → подтянуть сайты
            const msg = { role: m.role, content: m.content, created_at: m.created_at };
            return { ...prev, messages: [...prev.messages, msg] };
          }),
        onStatus: (status) =>
          sinksRef.current.setCurrent((prev) =>
            prev && prev.id === sessionId
              ? { ...prev, status: status as SessionRecord['status'] }
              : prev,
          ),
        onProgress: (p) => {
          sinksRef.current.setProgress(p);
          if (p.status !== 'waiting_user') sinksRef.current.setChallenge(null); // прошли — снять карточку
        },
        onChallenge: (c) => sinksRef.current.setChallenge(c),
        onDone: () => {
          detach();
          sinksRef.current.setProgress(null);
          sinksRef.current.setChallenge(null);
          reload(sessionId, true);
          sinksRef.current.onFinished();
        },
      });
    },
    [detach, reload],
  );

  return { attach, detach, loadSites };
}

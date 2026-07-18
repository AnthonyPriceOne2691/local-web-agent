import type {
  ChallengeWait,
  CrawlProgress,
  RunRecord,
  SessionListItem,
  SessionRecord,
  SseMessage,
} from './types'

async function asJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const body = await resp.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* keep HTTP status */
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

const post = (url: string, body: unknown) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const api = {
  listSessions: () =>
    fetch('/sessions').then((r) => asJson<{ sessions: SessionListItem[] }>(r)),
  createSession: (title = '', attended = false) =>
    post('/sessions', { title, attended }).then((r) => asJson<{ session_id: string }>(r)),
  resumeSession: (id: string) =>
    post(`/sessions/${id}/resume`, {}).then((r) => asJson<{ status: string }>(r)),
  getSession: (id: string) =>
    fetch(`/sessions/${id}`).then((r) => asJson<SessionRecord>(r)),
  postMessage: (id: string, content: string) =>
    post(`/sessions/${id}/messages`, { content }).then((r) => asJson<{ status: string }>(r)),
  cancelSession: (id: string) =>
    post(`/sessions/${id}/cancel`, {}).then((r) => asJson<{ status: string }>(r)),
  deleteSession: (id: string) =>
    fetch(`/sessions/${id}`, { method: 'DELETE' }).then((r) => asJson<{ deleted: string }>(r)),
  getRun: (id: string) => fetch(`/runs/${id}`).then((r) => asJson<RunRecord>(r)),
  reportUrl: (sessionId: string) => `/sessions/${sessionId}/report`,
  screenshotUrl: (runId: string, stepPos: number, profile = 'desktop') =>
    `/runs/${runId}/steps/${stepPos}/screenshot?profile=${profile}`,
}

export async function downloadReport(sessionId: string): Promise<void> {
  const resp = await fetch(api.reportUrl(sessionId))
  if (!resp.ok) throw new Error(`report: HTTP ${resp.status}`)
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `comparison_${sessionId}.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

export interface SessionEventHandlers {
  onMessage?: (m: SseMessage) => void
  onStatus?: (status: string) => void
  onProgress?: (p: CrawlProgress) => void
  onChallenge?: (c: ChallengeWait) => void
  onDone?: (status: string) => void
}

/** SSE-подписка (doc 15 v0.6). Возвращает unsubscribe. EventSource сам
 * реконнектит при обрыве; реплей дедупится по message.index на стороне UI. */
export function subscribeSessionEvents(
  sessionId: string,
  sinceMessages: number,
  h: SessionEventHandlers,
): () => void {
  const es = new EventSource(`/sessions/${sessionId}/events?since_messages=${sinceMessages}`)
  const on = <T,>(name: string, fn: (data: T) => void) =>
    es.addEventListener(name, (evt) => {
      try {
        fn(JSON.parse((evt as MessageEvent).data) as T)
      } catch {
        /* malformed event — skip */
      }
    })
  on<SseMessage>('message', (d) => h.onMessage?.(d))
  on<{ status: string }>('status', (d) => h.onStatus?.(d.status))
  on<CrawlProgress>('crawl_progress', (d) => h.onProgress?.(d))
  on<ChallengeWait>('challenge_wait', (d) => h.onChallenge?.(d))
  on<{ status: string }>('done', (d) => {
    es.close()
    h.onDone?.(d.status)
  })
  return () => es.close()
}

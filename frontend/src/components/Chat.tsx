import { useEffect, useRef, useState } from 'react'
import type { ChallengeWait, CrawlProgress, SessionRecord } from '../types'
import Message from './Message'
import StatusBadge from './StatusBadge'

interface Props {
  session: SessionRecord | null
  progress: CrawlProgress | null
  challenge: ChallengeWait | null
  banner: string
  sending: boolean
  attended: boolean
  onSend: (content: string) => void
  onCancel: () => void
  onResume: () => void
  onToggleAttended: (value: boolean) => void
}

const EXAMPLES = [
  {
    label: 'UC-1 · design compare',
    text: 'Вот 4 сайта: https://a.com, https://b.com, https://c.com, https://d.com — пройди по каждому и опиши дизайн, чем они отличаются друг от друга.',
  },
  {
    label: 'UC-2 · content compare',
    text: 'Конкуренты: https://x.com, https://y.com, https://z.com — найди статью про ставки на футбол и скажи, у кого самая полная и почему.',
  },
]

export default function Chat({
  session, progress, challenge, banner, sending, attended,
  onSend, onCancel, onResume, onToggleAttended,
}: Props) {
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const busy = session != null && ['running_tools', 'comparing'].includes(session.status)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [session?.messages.length, progress?.pages_visited, challenge])

  const submit = () => {
    const text = draft.trim()
    if (!text || sending || busy) return
    setDraft('')
    onSend(text)
  }

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
        {!session && (
          <div className="max-w-lg mx-auto mt-16 text-center">
            <div className="text-4xl mb-3">🔍</div>
            <h2 className="text-lg font-semibold mb-1">Paste URLs and describe the task</h2>
            <p className="text-sm text-slate-500 mb-6">
              The agent crawls each site sequentially (Playwright + local Ollama),
              then compares the results. Everything stays on this machine.
            </p>
            <div className="space-y-2 text-left">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.label}
                  onClick={() => setDraft(ex.text)}
                  className="w-full rounded-lg border border-slate-200 bg-white hover:border-blue-400 px-3 py-2 text-xs text-slate-600"
                >
                  <span className="font-semibold text-slate-800">{ex.label}</span>
                  <span className="block mt-0.5 line-clamp-2">{ex.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {session?.messages.map((m, i) => <Message key={i} message={m} />)}
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

      <footer className="shrink-0 border-t border-slate-200 bg-white p-3">
        <div className="flex gap-2 items-end">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            rows={Math.min(6, Math.max(1, draft.split('\n').length))}
            placeholder={busy ? 'Session is running — wait or cancel…' : 'URLs + task… (Enter to send)'}
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
            disabled={session != null || busy}
            onChange={(e) => onToggleAttended(e.target.checked)}
            className="accent-blue-600"
          />
          Attended-режим (пройти проверки вручную) — задаётся при старте новой сессии
        </label>
      </footer>
    </main>
  )
}

function ChallengeCard({ challenge, onResume }: {
  challenge: ChallengeWait
  onResume: () => void
}) {
  const host = new URL(challenge.start_url).host
  const isLogin = challenge.kind === 'login_wall'
  const isConfirm = challenge.kind === 'confirm_submit'
  const title = isConfirm ? 'Подтвердите действие' : isLogin ? 'Нужен вход' : 'Нужна проверка'
  const body = isConfirm
    ? 'Агент хочет отправить форму на этой странице. Проверь в открытом браузере и подтверди — тогда агент нажмёт submit.'
    : isLogin
      ? 'Сайт требует входа. Я открыл браузер — залогинься сам в появившемся окне (пароль остаётся у тебя, агент его не видит и не хранит), потом нажми «Продолжить».'
      : `Сайт показал anti-bot проверку (${challenge.kind}). Я открыл браузер — пройди её в появившемся окне, потом нажми «Продолжить».`
  const btn = isConfirm ? '✓ Подтвердить отправку' : isLogin ? '✓ Я вошёл — продолжить' : '✓ Я прошёл — продолжить'
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-3 text-sm text-amber-900">
      <div className="font-semibold mb-1">⏸ {title} — {host}</div>
      <p className="text-xs text-amber-800 mb-2.5">{body}</p>
      <button
        onClick={onResume}
        className="rounded-md bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 text-xs font-medium"
      >
        {btn}
      </button>
    </div>
  )
}

function ProgressCard({ progress }: { progress: CrawlProgress }) {
  const pct = Math.min(100, Math.round((progress.pages_visited / progress.max_pages) * 100))
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
      <div className="flex items-center gap-2 mb-1.5">
        <Spinner />
        <span className="font-medium truncate">Crawling {progress.start_url}</span>
        <span className="ml-auto tabular-nums">
          {progress.pages_visited}/{progress.max_pages} pages
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-blue-100 overflow-hidden">
        <div className="h-full bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      {progress.current_url && (
        <div className="mt-1 truncate text-blue-600">{progress.current_url}</div>
      )}
    </div>
  )
}

function Spinner() {
  return (
    <span className="inline-block size-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
  )
}

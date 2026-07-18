import type { SessionListItem } from '../types'
import StatusBadge from './StatusBadge'

interface Props {
  sessions: SessionListItem[]
  currentId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
}

export default function Sidebar({ sessions, currentId, onSelect, onNew, onDelete }: Props) {
  return (
    <aside className="w-64 shrink-0 bg-slate-900 text-slate-100 flex flex-col">
      <div className="p-3 border-b border-slate-700 flex items-center justify-between">
        <div>
          <div className="font-semibold text-sm">Local Web Agent</div>
          <div className="text-[11px] text-slate-400">research chat · local only</div>
        </div>
        <button
          onClick={onNew}
          title="New chat"
          className="rounded-md bg-blue-600 hover:bg-blue-500 px-2.5 py-1.5 text-sm font-medium"
        >
          +
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto py-1">
        {sessions.length === 0 && (
          <div className="px-3 py-4 text-xs text-slate-500">No sessions yet</div>
        )}
        {sessions.map((s) => (
          <div
            key={s.session_id}
            onClick={() => onSelect(s.session_id)}
            className={`group mx-1.5 my-0.5 rounded-md px-2 py-2 cursor-pointer text-sm
              ${s.session_id === currentId ? 'bg-slate-700' : 'hover:bg-slate-800'}`}
          >
            <div className="flex items-center gap-1.5">
              <span className="flex-1 truncate">{s.title || 'Untitled session'}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  if (confirm(`Delete session "${s.title || s.session_id}"?`)) onDelete(s.session_id)
                }}
                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-400 text-xs px-1"
                title="Delete session"
              >
                ✕
              </button>
            </div>
            <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-400">
              <StatusBadge status={s.status} />
              <span>{s.runs} runs</span>
            </div>
          </div>
        ))}
      </nav>
    </aside>
  )
}

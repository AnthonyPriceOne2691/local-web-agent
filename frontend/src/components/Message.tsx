import type { SessionMessage } from '../types';

export default function Message({ message }: { message: SessionMessage }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-blue-600 text-white px-3.5 py-2 text-sm whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }
  if (message.role === 'assistant') {
    return (
      <div className="flex">
        <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-white border border-slate-200 px-3.5 py-2 text-sm whitespace-pre-wrap break-words shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }
  // tool / system notes (M-S1) — компактная строка
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-slate-500 font-mono px-1">
      <span>⚙</span>
      <span className="truncate">{message.content}</span>
    </div>
  );
}

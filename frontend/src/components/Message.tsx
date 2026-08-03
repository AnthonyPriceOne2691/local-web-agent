import type { SessionMessage } from '../types';

export default function Message({ message }: { message: SessionMessage }) {
  if (message.role === 'user') {
    return (
      <div className="rise-in flex justify-end">
        <div className="accent-surface max-w-[75%] rounded-3xl rounded-br-lg px-4 py-2.5 text-[14px] leading-relaxed break-words whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }
  if (message.role === 'assistant') {
    return (
      <div className="rise-in flex">
        <div className="glass max-w-[85%] rounded-3xl rounded-bl-lg px-4 py-3 text-[14px] leading-relaxed break-words whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }
  /* Шаги агента: тихая строка, а не сообщение — это фон работы, не разговор.
     Раньше здесь стоял моношрифт и значок ⚙, из-за чего служебные заметки
     выглядели важнее ответов. */
  return (
    <p className="text-faint rise-in flex items-baseline gap-2 px-1 text-[11.5px]">
      <span aria-hidden className="text-[var(--color-accent-soft)]">
        ·
      </span>
      <span className="truncate">{message.content}</span>
    </p>
  );
}

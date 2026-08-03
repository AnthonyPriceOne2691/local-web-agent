import { useState } from 'react';

import Chat from './components/Chat';
import Inspector from './components/Inspector';
import Sidebar from './components/Sidebar';
import { useSession } from './useSession';

type Pane = 'chats' | 'chat' | 'sites';

/** Только композиция экрана: три стеклянных слоя над градиентным полотном.
 *  Вся логика — в `useSession`.
 *
 *  На узком окне три колонки не помещаются: чат сжимался до полутора сотен пикселей,
 *  текст обрезался, инспектор уходил за экран. Поэтому ниже `lg` показывается **одна**
 *  панель за раз, а переключатель внизу выбирает какую. Скрывать боковые панели без
 *  переключателя было нельзя — список чатов и найденное стали бы недостижимы. */
export default function App() {
  const s = useSession();
  const [pane, setPane] = useState<Pane>('chat');

  return (
    <div className="flex h-full flex-col gap-3 p-3 lg:flex-row">
      <div
        className={`${pane === 'chats' ? 'flex' : 'hidden'} min-h-0 flex-1 lg:flex lg:flex-none`}
      >
        <Sidebar
          sessions={s.sessions}
          currentId={s.current?.id ?? null}
          onSelect={(id) => {
            s.select(id);
            setPane('chat');
          }}
          onNew={() => {
            s.startNew();
            setPane('chat');
          }}
          onDelete={s.remove}
        />
      </div>

      <div className={`${pane === 'chat' ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-1 lg:flex`}>
        <Chat
          session={s.current}
          progress={s.progress}
          challenge={s.challenge}
          error={s.error}
          sending={s.sending}
          busy={s.busy}
          watchBrowser={s.watchBrowser}
          onSend={s.send}
          onStop={s.stop}
          onResume={s.resume}
          onDismissError={s.dismissError}
          onToggleWatchBrowser={s.setWatchBrowser}
        />
      </div>

      <div
        className={`${pane === 'sites' ? 'flex' : 'hidden'} min-h-0 flex-1 lg:flex lg:flex-none`}
      >
        <Inspector session={s.current} runs={s.runs} progress={s.progress} />
      </div>

      <PaneSwitch pane={pane} onPick={setPane} siteCount={Object.keys(s.runs).length} />
    </div>
  );
}

/** Переключатель панелей — только на узком окне (`lg:hidden`). */
function PaneSwitch({
  pane,
  onPick,
  siteCount,
}: {
  pane: Pane;
  onPick: (p: Pane) => void;
  siteCount: number;
}) {
  const items: { key: Pane; label: string }[] = [
    { key: 'chats', label: 'Chats' },
    { key: 'chat', label: 'Conversation' },
    { key: 'sites', label: siteCount ? `Sites · ${siteCount}` : 'Sites' },
  ];
  return (
    <nav className="glass-panel flex shrink-0 gap-1 rounded-[var(--radius-glass)] p-1 lg:hidden">
      {items.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onPick(key)}
          aria-pressed={pane === key}
          className={`focus-ring press flex-1 rounded-2xl px-3 py-2 text-[12px] font-medium
            ${pane === key ? 'glass text-ink' : 'text-soft glass-slot'}`}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}

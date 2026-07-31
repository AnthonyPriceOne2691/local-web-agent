import Chat from './components/Chat';
import Inspector from './components/Inspector';
import Sidebar from './components/Sidebar';
import { useSession } from './useSession';

/** Только композиция экрана: три стеклянных слоя над градиентным полотном.
 *  Вся логика — в `useSession`. */
export default function App() {
  const s = useSession();

  return (
    <div className="flex h-full gap-3 p-3">
      <Sidebar
        sessions={s.sessions}
        currentId={s.current?.id ?? null}
        onSelect={s.select}
        onNew={s.startNew}
        onDelete={s.remove}
      />
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
      <Inspector session={s.current} runs={s.runs} progress={s.progress} />
    </div>
  );
}

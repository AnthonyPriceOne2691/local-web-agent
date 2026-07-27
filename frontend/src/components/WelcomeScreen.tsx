const EXAMPLES = [
  {
    label: 'UC-1 · design compare',
    text: 'Вот 4 сайта: https://a.com, https://b.com, https://c.com, https://d.com — пройди по каждому и опиши дизайн, чем они отличаются друг от друга.',
  },
  {
    label: 'UC-2 · content compare',
    text: 'Конкуренты: https://x.com, https://y.com, https://z.com — найди статью про ставки на футбол и скажи, у кого самая полная и почему.',
  },
];

/** Пустое состояние чата: что умеет агент + готовые примеры задач. */
export default function WelcomeScreen({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="max-w-lg mx-auto mt-16 text-center">
      <div className="text-4xl mb-3">🔍</div>
      <h2 className="text-lg font-semibold mb-1">Paste URLs and describe the task</h2>
      <p className="text-sm text-slate-500 mb-6">
        The agent crawls each site sequentially (Playwright + local Ollama), then compares the
        results. Everything stays on this machine.
      </p>
      <div className="space-y-2 text-left">
        {EXAMPLES.map((ex) => (
          <button
            key={ex.label}
            onClick={() => onPick(ex.text)}
            className="w-full rounded-lg border border-slate-200 bg-white hover:border-blue-400 px-3 py-2 text-xs text-slate-600"
          >
            <span className="font-semibold text-slate-800">{ex.label}</span>
            <span className="block mt-0.5 line-clamp-2">{ex.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

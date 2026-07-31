/** Пустой экран должен объяснять не устройство агента, а что человеку сделать.
 *  Прежние подписи («UC-1 · design compare») были кодами из дизайн-доков. */
const EXAMPLES = [
  {
    title: 'Compare how competitors look',
    text: 'Take a look at https://example.com, https://example.org and https://example.net — describe how each site looks and what makes them different.',
  },
  {
    title: 'Find who covers a topic best',
    text: 'Here are three blogs: https://example.com, https://example.org, https://example.net — find the article about football betting on each and tell me whose is the most thorough, and why.',
  },
  {
    title: 'Dig out contact details',
    text: 'Find the editorial contact email on https://example.com — quote the page it came from.',
  },
];

export default function WelcomeScreen({ onPick }: { onPick: (text: string) => void }) {
  return (
    /* Центрируем по вертикали: на первом скриншоте блок висел под шапкой, а под
       ним оставалась половина экрана пустоты. */
    <div className="mx-auto flex h-full max-w-xl flex-col justify-center py-6">
      <div className="text-center">
        <h2 className="text-[22px] font-semibold tracking-tight">
          Paste a few links, say what you need
        </h2>
        <p className="text-soft mx-auto mt-2 max-w-md text-[13.5px] leading-relaxed">
          The agent opens each site in a real browser, reads its way to the answer and quotes where
          it found it. Everything runs on this Mac — no site data and no page text leaves the
          machine.
        </p>
      </div>

      <div className="mt-6 space-y-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex.title}
            onClick={() => onPick(ex.text)}
            className="glass-quiet glass-hover focus-ring block w-full rounded-2xl px-4 py-3 text-left"
          >
            <span className="block text-[13px] font-medium">{ex.title}</span>
            <span className="text-faint mt-1 block line-clamp-2 text-[12px] leading-relaxed">
              {ex.text}
            </span>
          </button>
        ))}
      </div>

      <p className="text-faint mt-5 text-center text-[11.5px] leading-relaxed">
        It can also act on a page — fill a form, sign in, place an order. Anything that can&apos;t
        be undone stops and waits for you to press the button yourself.
      </p>
    </div>
  );
}

import type { ChallengeWait } from '../types';

/** Тексты паузы по виду ожидания (doc 24/25). Таблица вместо вложенных тернарников:
 *  добавить пятый вид = добавить строку, а не ещё один уровень `? :`. */
const COPY: Record<string, { title: string; button: string; body: (c: ChallengeWait) => string }> =
  {
    // Tier 3: агент подготовил необратимый шаг, но кнопку жмёт ЧЕЛОВЕК
    handoff: {
      title: 'Финальный шаг — за тобой',
      button: '✓ Готово — продолжить',
      body: (c) =>
        `Я подготовил необратимый шаг${c.action ? `: ${c.action}` : ''}. Такую кнопку агент не нажимает — нажми её сам в открытом браузере (или не нажимай, если передумал), потом вернись и нажми «Готово».`,
    },
    // Tier 2: подтверждение в чате, submit нажмёт агент
    confirm_submit: {
      title: 'Подтвердите действие',
      button: '✓ Подтвердить отправку',
      body: (c) =>
        `Агент хочет отправить форму${c.action ? ` (${c.action})` : ' на этой странице'}. Проверь в открытом браузере и подтверди — тогда агент нажмёт submit.`,
    },
    login_wall: {
      title: 'Нужен вход',
      button: '✓ Я вошёл — продолжить',
      body: () =>
        'Сайт требует входа. Я открыл браузер — залогинься сам в появившемся окне (пароль остаётся у тебя, агент его не видит и не хранит), потом нажми «Продолжить».',
    },
  };

/** anti-bot проверка — дефолт: kind приходит с бэкенда и может быть любым. */
const CAPTCHA = {
  title: 'Нужна проверка',
  button: '✓ Я прошёл — продолжить',
  body: (c: ChallengeWait) =>
    `Сайт показал anti-bot проверку (${c.kind}). Я открыл браузер — пройди её в появившемся окне, потом нажми «Продолжить».`,
};

export default function ChallengeCard({
  challenge,
  onResume,
}: {
  challenge: ChallengeWait;
  onResume: () => void;
}) {
  const host = new URL(challenge.start_url).host;
  const copy = COPY[challenge.kind] ?? CAPTCHA;
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-3 text-sm text-amber-900">
      <div className="font-semibold mb-1">
        ⏸ {copy.title} — {host}
      </div>
      <p className="text-xs text-amber-800 mb-2.5">{copy.body(challenge)}</p>
      <button
        onClick={onResume}
        className="rounded-md bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 text-xs font-medium"
      >
        {copy.button}
      </button>
    </div>
  );
}

# Active delivery status

- **slug:** real-site-calibration
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** verify
- **builder:** agent:claude-code
- **verifier:** human:anthony
- **human_ok_spec:** n/a
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
  <!-- CI есть; гейт мержа в репо (merge_guard + pre-push). Серверная защита ветки
       платная для приватного репо, поэтому force-push в main и обход админом не
       закрыты — остаток в delivery/STACK-ACCEPTANCE.md § Остатки. -->
- **worktree:** none (ветка `fix/real-site-calibration`)
- **hooks:** claude
- **stack-selftest:** external (Prepare/)
- **blockers:** —  <!-- приоритет задан владельцем: real-site прогон -->
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) · `tier3-exit-smoke` (S) ·
`nav-model-split` (S) · `synth-speed` (S) · `session-throughput` (S, закрыта
**частично**) · `ui-liquid-glass` (S) — все слиты через `merge_guard`; CI на main
зелёный. Артефакты в `delivery/archive/`.

## Backlog гейтов

- [x] **secrets-scanner** — `detect-secrets`, baseline пустой.
- [x] **`ruff-format`** — подключён, стилевой прогон в `afbd5f4`.
- [x] **Молчаливые `except`** — baseline 20 → 3 сайта (только `scripts/spike/**`).
- [x] **mypy-заглушки** сняты; **mypy → strict** ✅ (86 модулей).
- [x] **Diff-coverage** ✅ прогнан на реальном диффе кода (PR #7).
- [ ] **Сложность функций** (`C901`/`PLR09xx`, 10 модулей) — рефакторинг оркестратора.
- [x] **UI-рефактор** ✅ (поставка `ui-liquid-glass`): `App.tsx` → композиция,
      логика в `useSession` + `useSessionStream`.

## Хвосты из session-throughput (перенесены, не потеряны)

- `think:false` **без** схемы на `compare` — потолок ≈ 7 % сессии. Замер дешёвый:
  входы для A/B уже в БД, скрипт разложения написан.
- Cooldown 30 s при N ≥ 4 — нужен ли сейчас. Только с замером троттлинга, иначе
  «ускорение» обернётся деградацией на длинной сессии.
- `article.word_count` модель заполняет неверно (14 при статье на ~400 слов).

## Контекст поставки

Владелец: «сходи в сеть и вытащи для нашего проекта несколько сайтов и прогони»,
затем два уточнения по ходу прогона: (1) при anti-bot он сам проставит галочки,
(2) **браузер не должен висеть перед глазами без надобности** — либо скрывать сразу,
либо не показывать, если действия человека не нужны.

Первый же real-site прогон (`docs.astro.build`, `gohugo.io`, `www.11ty.dev`,
задача про getting-started) оправдал калибровку: он вскрыл дефект, который на
фикстурах невидим в принципе, потому что для `127.0.0.1` robots.txt не
запрашивается вовсе.

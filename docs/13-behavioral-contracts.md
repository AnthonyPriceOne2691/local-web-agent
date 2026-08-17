# 13 — Behavioral Contracts (ABC-lite)

> Local Web Agent · Design doc · **v0.10** · 2026-08-06  
> **Источник правды (контроль модели):** Bhardwaj, «Agent Behavioral Contracts: Formal Specification and Runtime Enforcement for Reliable Autonomous AI Agents», arXiv:[2602.22302](https://arxiv.org/abs/2602.22302) — локальная копия: `/Users/anthony/Documents/2602.22302v1.pdf`  
> Контракт **C = (P, I, G, R)**, hard/soft split, bounded recovery, **runtime enforcement на уровне действий** (до Playwright)

## Что берём из full ABC, что нет

| Идея из paper | У нас | Почему |
|---------------|-------|--------|
| C = (P, I_hard, I_soft, G_hard, G_soft, R) | ✅ полностью | Ядро фреймворка; контроль browsing-agent |
| **Action-level enforcement** (не только output filter) | ✅ | Paper §2.5: text-level alignment **не переносится** на tool-call safety — агент **действует** через Playwright |
| Hard = никогда; soft = transient + recovery ≤ k | ✅ k = 2 replan + fallback | Lemma 3.10: без recovery комплаенс падает экспоненциально; crawl T ≈ 10–30 steps |
| Метрики **до** recovery («transparency effect») | ✅ | Violation log фиксирует сырое поведение LLM |
| ContractSpec YAML DSL (paper §5) | ✅ упрощённый YAML в `data/contracts/` | Декларативность; enforcer отклоняет unknown `check` |
| Overhead < 10 ms/action (Prop. 4.15) | ✅ | URL parse, set membership, counters — O(1) |
| Drift score D(t) = compliance-gap + JSD | ⚠️ только compliance (violation counters) | JSD по action distribution — post-MVP |
| (p, δ, k)-satisfaction, Drift Bounds Theorem | ❌ | Solo tool; порог: hard violations ≥ 3/run → tighten |
| AgentAssert library (paper §5) | ❌ | Свой `ContractEnforcer`; reference impl patent pending |
| AgentContract-Bench | ❌ | Свой Phase 0/2 benchmark (doc 19, doc 06) |
| Multi-agent composition (Theorem 4.9) | ❌ | Один crawl agent; crawl → synthesis handoff через precondition |

## Зачем

**Промпт недостаточен.** LLM-navigation drift’ит за multi-step crawl: уходит на чужой домен, «выдумывает» URL, зацикливается на legal/cookie, submit’ит формы, возвращает факты без evidence.

**Решение (из paper):** Agent Behavioral Contracts — **formal runtime behavioral specification** с enforcement **перед каждым действием в browser**, не post-hoc фильтрацией текста.

**Contracts ≠ model quality:** Qwen решает *куда* идти; контракт решает *можно ли выполнить*. Orchestrator держит *структуру* (лимиты, visited set).

```
Orchestrator (P, G hard — структура)  →  LLM (propose action)  →  Contract Enforcer  →  Playwright
        │                                      │                          │
   max pages, depth, robots              navigate where?            shield: allowed?
```

**Два слоя (обязательно оба):**

| Слой | Кто | Что контролирует |
|------|-----|------------------|
| **Orchestrator** | Детерминированный код | pages_visited, depth, visited set, rate limit, state machine |
| **Contract Enforcer** | YAML + pure Python | Каждое proposed action LLM до execution |

LLM **не решает** budget страниц — только orchestrator (аналог FR-7.3 в Voice Interview Coach).

---

## Модель контракта

**Definition 3.1 (paper):** C = (P, I_hard, I_soft, G_hard, G_soft, R)

| Компонент | У нас | Пример |
|-----------|-------|--------|
| **P** Preconditions | Перед стартом run | Valid URL; robots.txt fetched; browser ready |
| **I_hard** Invariants | На каждом step / весь run | Same domain; no auth; URL ∈ snapshot |
| **I_soft** Invariants | Желательно; recovery OK | Avoid privacy pages; prefer task-relevant links |
| **G_hard** Governance | На каждое **действие** | max_pages; rate_limit; robots disallow |
| **G_soft** Governance | Мягкие лимиты | Prefer shorter paths |
| **R** Recovery | При fail | replan → link scorer → partial stop |

**Hard** — reject action, **не** выполнять в Playwright, recovery обязателен.  
**Soft** — log + replan hint; допустимо transient violation с recovery ≤ k (MVP: k = 2 replan per step).

---

## Mode: Crawl (navigation loop)

### Preconditions (P)

| ID | Rule | Check |
|----|------|-------|
| P-1 | Valid `start_url` (http/https) | config parse |
| P-2 | Task non-empty, ≤ 2000 chars | config |
| P-3 | Playwright browser ready | INIT state |
| P-4 | If `respect_robots`: robots.txt fetched or logged missing | INIT |
| P-5 | Ollama navigation model reachable | health check |

### Hard invariants (I_hard)

| ID | Rule | Enforcement |
|----|------|-------------|
| I-H1 | **Allowed domains only** — navigate target ∈ allowed set | URL parser vs config |
| I-H2 | **No form submit** — no submit-click, no POST, no login-click | reject `submit`/login actions; Tier 1 `click` разрешён только по не-submit элементу (I-H10, doc 25) |
| I-H3 | **No authentication** — агент не логинится сам (no fill password/email). Attended: login_wall → пауза, **человек** логинится в видимом браузере (Tier 2, doc 25), агент паролей не касается | blocker detect + attended pause / reject ACT |
| I-H4 | **No file download execute** | Playwright download blocked |
| I-H6 | **Never fabricate URLs** — navigate only to URL ∈ **CandidateQueue** = snapshot links ∪ slug probes из `path_hints` ∪ sitemap URLs (doc 21) ∪ `{start_url}` | set membership on normalized URL |
| I-H7 | **Action schema valid** — JSON parses to `navigate \| extract_now \| click \| stop` | Action Planner |
| I-H8 | **No private network / bad scheme** — only `http(s)`; reject loopback, RFC1918, link-local, `.local`/`.internal` hosts (защита от SSRF на локальный API/роутер) unless `--allow-private` | URL parse + IP range check, < 1 ms |
| I-H9 | **Post-redirect re-check** — после `goto` финальный URL повторно проверяется на I-H1/I-H8; off-domain redirect → snapshot discarded, URL помечен `redirect_offsite`, вернуться к queue. **Исключение — step 0:** редирект первой навигации переопределяет `allowed_domains` от landing URL (переезд домена; doc 04 INIT), I-H8 применяется всё равно | orchestrator after navigation |
| I-H10 | **Click safety (doc 25)** — `click` по `element_index` ∈ `interactive_elements`. Не-submit → автономно (Tier 1). **Submit → под attended-подтверждением** (Tier 2: `ctx.attended` пропускает, `confirm_action` в ACT); без attended → reject. Password → login (attended) | enforcer: index + kind; `ctx.attended` |
| I-H11 | **Fill safety (Tier 2, doc 25)** — `fill` только в текстовые поля (`element_index` ∈ `interactive_elements`, kind/type ∈ text/email/search/tel/url/number/textarea), **никогда в password** (креды вводит человек, attended) | enforcer: index + kind check |
| I-H12 | **Destructive click = handoff (Tier 3, doc 25)** — click по элементу с destructive-сигналом в label (`destructive_signals` словарь: buy/pay/оплат/удал/…) агент **не исполняет никогда**: unattended → reject; attended → `handoff_action` (пауза kind=`handoff`, **человек жмёт кнопку сам** в видимом браузере) → resume → re-observe. Проверяется **до** attended-пропуска submit из I-H10 (submit «Оплатить» не может пройти через confirm, где нажал бы агент) | enforcer: label match до I-H10; ACT-развилка handoff |

> I-H5 (evidence) относится к synthesis pass — см. ниже.  
> **Замечание к I-H6:** LLM по-прежнему не может *изобрести* URL — slug probes и sitemap URLs детерминированно конструируются оркестратором (doc 21), LLM лишь выбирает из готовой очереди. Формулировка «href ∈ snapshot links» из v0.4 противоречила P2/P3 slug probes doc 21 — исправлено.  
> **Cookie-banner dismissal (D-11 closed, doc 22):** detect → CSS-hide (default; ноль взаимодействий, согласие не даётся) → CMP-click reject-first (fallback) — **детерминированный шаг оркестратора в OBSERVE**, не LLM-действие. Через enforcer не проходит и I-H2 не нарушает: LLM не может предложить клик; селекторы фиксированы в `data/navigation/consent_selectors.yaml`.

### Hard governance (G_hard)

| ID | Rule | Enforcement |
|----|------|-------------|
| G-H1 | **max_pages** | orchestrator counter — **not LLM** |
| G-H2 | **max_depth** | orchestrator **hop depth** (навигационные переходы, не сегменты URL — doc 04 policy #2) |
| G-H3 | **No revisit** | visited set **∪ attempted set** (см. ниже) |
| G-H4 | **rate_limit_ms** | sleep in ACT |
| G-H5 | **robots.txt** | robotparser before navigate |
| G-H6 | **page_timeout_ms** | Playwright timeout |
| G-H7 | **One action per PLAN step** | parser rejects batch actions |

> **Замечание к G-H3 (v0.10):** множество «уже были» — это `visited ∪ attempted`, и разделение
> не косметическое. `visited` хранит URL **прочитанных страниц** (`snapshot.url`, то есть адрес
> ПОСЛЕ редиректа) — на нём же считается бюджет G-H1. `attempted` хранит то, **куда агент
> ходил**: запрошенные URL, уведённые редиректом, и цели, до которых дойти не удалось (две
> неудачных попытки `goto`, offsite-редирект, robots).
>
> Дыру нашёл замер журнала прогонов (doc 26 § T-3l): пока сайт редиректит A → B, ссылка A
> остаётся «непосещённой» и проходит G-H3 **бесконечно** — на `sports.ru` три шага из восьми
> ушли на одну и ту же страницу, `lenta.ru/archive` повторялся в трёх прогонах подряд.
> `contract_violations` при этом были пустыми: правило честно не срабатывало.
>
> Почему не сложить всё в одно множество: алиас редиректа тогда съедал бы страницу из лимита
> `max_pages`. Соответственно `ctx.pages_visited` считается **только** по `visited`.
> Алиасы записываются в `metadata.redirect_aliases` и исключаются из «не удалось открыть»
> (`unreached_urls`) — иначе агент сообщил бы человеку, что не дошёл до страницы, которую
> прочитал.

### Soft invariants (I_soft)

| ID | Rule | Recovery | MVP |
|----|------|----------|-----|
| I-S1 | Prefer same-site over external (even if `--allow-external`) | log warning | ✅ |
| I-S2 | Legal pages (`/privacy`, `/terms`) — **soft avoid** by default; **boost** when `task_intent=contact` (SEOLB: operator contact on legal pages) | replan hint OR +8 link score | ✅ |
| I-S3 | Prefer links matching task keywords (pricing, contact, about) | soft score in link fallback | ✅ |

### Soft governance (G_soft)

| ID | Rule | Recovery |
|----|------|----------|
| G-S1 | Stop after 3 pages with zero new relevant links | orchestrator → SYNTHESIZE |
| G-S2 | If `task_progress: likely_complete` but action ≠ stop — nudge replan | inject «confirm or stop» |

### Recovery (R)

| Step | Action |
|------|--------|
| 1 | Reject + violation log + replan with rejection reason (max **2** per step) |
| 2 | Link scorer fallback (orchestrator, deterministic) |
| 3 | Stop run with `status: partial` |

Paper Lemma 3.10: recovery превращает экспоненциальный decay комплаенса в линейный — для crawl run с T ≈ 10 steps это критично.

---

## Mode: Synthesis (post-crawl JSON pass)

Отдельный контракт для R1 extraction — **не Playwright**, schema validator + evidence verifier.

### Preconditions (P)

| ID | Rule | Check |
|----|------|-------|
| P-S1 | ≥ 1 page snapshot stored | run store |
| P-S2 | Crawl status ≠ `failed` | orchestrator |

### Hard invariants (I_hard)

| ID | Rule | Enforcement |
|----|------|-------------|
| S-H1 | Valid `ExtractionResult` JSON schema | Pydantic |
| S-H2 | Every `high` confidence fact has non-empty `evidence[].quote` | validator |
| S-H3 | Quotes ⊆ snapshot text (fuzzy match ≥ 0.85, rapidfuzz) — проверка **in-memory во время synthesis** (снапшоты ещё загружены), не чтением с диска: работает и при `--no-artifacts`; артефакты — только для аудита | verify pass |
| S-H4 | No fact without any snapshot source URL | schema |
| S-H5 | **Non-empty content after thinking separation** — Ollama ≥ 0.9 отдаёт thinking отдельным полем (`think: true` → `message.thinking`); `strip_thinking()` остаётся fallback'ом при утечке `<think>` в content | hard fail → retry R1 |

### Hard governance (G_hard)

| ID | Rule | Enforcement |
|----|------|-------------|
| S-G1 | `not_found[]` required when task aspect missing | prompt + validator |
| S-G2 | Max 20 facts per run | truncate + log |
| S-G3 | No PII patterns unless task explicitly asks for public contact | regex flag (warn) |

### Recovery (R)

| Violation | Recovery |
|-----------|----------|
| Invalid JSON | Retry R1 once with parse error |
| high without quote | Downgrade to medium or reject fact |
| Quote not in snapshot | Remove fact → add to not_found |
| Empty after strip_thinking | Retry with higher num_predict |

Voice contract enforcer **не применяется** к synthesis — отдельный `SynthesisValidator`.

---

## Mode: Vision batch (pre-synthesis, no Playwright)

**Shield для VisionLoader** — не path injection, не произвольные файлы. Enforcer **не** вызывает VLM; только валидирует inputs batch job.

### Preconditions (P)

| ID | Rule | Check |
|----|------|-------|
| P-V1 | Run has ≥1 screenshot artifact OR skip batch | run store |
| P-V2 | VLM model reachable (if vision_enabled ≠ never) | health |
| P-V3 | Browser closed before VLM load | orchestrator state = VISION_BATCH |

### Hard invariants (I_hard)

| ID | Rule | Enforcement |
|----|------|-------------|
| V-H1 | **Path allowlist** — load only paths ∈ `PageSnapshot.screenshots[].relative_path` for this `run_id` | VisionLoader.resolve |
| V-H2 | **No path traversal** — reject `..`, absolute paths, symlinks outside artifacts | loader normalize |
| V-H3 | **Max file size** — PNG ≤ **5 MB** | loader stat |
| V-H4 | **Valid profile** — analyze only `desktop` \| `tablet` \| `mobile` | analyzer |
| V-H5 | **Call budget** — `vision_calls_total ≤ max_vision_calls` | orchestrator counter |

### Hard governance (G_hard)

| ID | Rule | Enforcement |
|----|------|-------------|
| V-G1 | **max_vision_pages** — queue size cap (doc 23) | orchestrator |
| V-G2 | **Timeout** — 45 s per VLM call | client |
| V-G3 | **No user-supplied image paths** in API/CLI — only internal artifacts | API schema |

### Recovery (R)

| Violation | Recovery |
|-----------|----------|
| V-H1 path not in snapshot | skip call; `status: skipped` |
| V-H3 oversize | skip; log |
| V-G2 timeout | 1 retry → `status: failed` |
| Invalid JSON | 1 retry repair prompt → `degraded` |
| OOM | abort remaining batch; `vision_partial: true` |

### Synthesis evidence rules (vision-aware)

Updates to synthesis hard invariants:

| ID | Rule | Enforcement |
|----|------|-------------|
| S-H3a | DOM **high** facts: quote ⊆ snapshot `main_text` (fuzzy ≥ 0.85) | unchanged |
| S-H3b | Vision-only facts: **no quote required**; require `evidence.source: vision` + `vision_insight_ref` | schema |
| **S-H6** | Vision-only fact **cannot** be `confidence: high` unless DOM cross-validates same value | validator |
| S-H7 | `design_tokens`, layout, colors — may be `medium` from vision alone | allowed |

`evidence` extension:

```json
{
  "url": "https://example.com/pricing",
  "quote": "",
  "source": "vision",
  "vision_insight_ref": {"step_index": 2, "profile": "desktop"},
  "screenshot_path": "screenshots/002_pricing_desktop.png"
}
```

Cross-validated (same value in DOM + vision) → **high** allowed with both quotes/refs.

---

## Runtime pipeline (shield before Playwright)

Paper §2.3: **shielding** — intercept unsafe actions before execution. У нас: enforcer между LLM и Playwright (аналог enforcer перед TTS в Voice Interview Coach).

```
PageSnapshot + task + budget
        │
        ▼
   LLM (Qwen) → JSON AgentAction
        │
        ▼
   parse AgentAction
        │
        ▼
┌───────────────────────────────────┐
│ Contract Enforcer (per action)     │
│  · I-H1 domain                     │
│  · I-H6 url ∈ known_links          │
│  · I-H2 no submit                  │
│  · G-H5 robots                     │
│  · orchestrator pre-checks passed  │
└───────┬───────────────┬───────────┘
     pass│               │fail
        ▼               ▼
 Playwright.goto    log violation (pre-recovery)
                         │
                    replan ≤2 → link_scorer → partial stop
```

**Инвариант:** **ни одно не-валидированное действие не попадает в Playwright.**

Latency: enforcer adds **< 10 ms** — не влияет на crawl budget (dominated by page load + LLM).

---

## Violation event schema

Фиксируется **до recovery** (paper §7.1 transparency):

```json
{
  "run_id": "...",
  "step_index": 4,
  "state": "VALIDATE",
  "constraint_id": "I-H6",
  "severity": "hard",
  "message": "URL not in snapshot links",
  "proposed_action": {"action": "navigate", "url": "https://example.com/admin"},
  "recovery": "replan",
  "recovered": true,
  "ts": "2026-07-05T..."
}
```

Per-run aggregates (в `crawl_runs.metadata_json`):

| Metric | Use |
|--------|-----|
| `hard_violations` | Diagnostics; drift signal |
| `soft_violations` | Prompt tuning |
| `recovery_success_rate` | Quality of R |
| `fallback_count` | link_scorer invocations |

---

## Recovery strategies

| Violation | Recovery (order) |
|-----------|------------------|
| I-H1 external domain | Replan: «Choose same-domain link only» → link scorer |
| I-H6 fabricated URL | Replan: «URL must be from links list» → link scorer |
| I-H8 private network URL | Skip URL, log; no replan needed (кандидат просто исключается из queue) |
| I-H9 off-domain redirect | Discard snapshot; mark URL `redirect_offsite`; next candidate from queue |
| I-H2 submit attempt | Replan: «Navigate only, no forms» |
| I-H10 unsafe click (submit/login element) | Reject; replan «click only non-submit element, or navigate» |
| I-H12 destructive click unattended | Reject; replan «irreversible step needs attended mode — navigate or stop» |
| I-H12 destructive click attended | Не reject: ACT → handoff-пауза (человек жмёт сам) → resume → re-observe |
| G-H5 robots disallow | Skip URL; pick next link from scorer |
| G-H1 max pages | Force `stop` → SYNTHESIZE |
| Blocker (captcha/login) | No recovery → `status: blocked` |
| 2× replan fail same step | link_scorer → navigate best link or stop |

---

## ContractSpec files (repo)

**Статус:** planned — создаются в Phase 2; schema фиксируется здесь.

```
local-web-agent/
└── data/
    └── contracts/
        ├── crawl.contract.yaml       # navigation ACT rules
        ├── synthesis.contract.yaml   # ExtractionResult rules
        ├── vision.contract.yaml      # VisionLoader batch rules (doc 23)
        └── crawl_forbidden.txt       # URL path patterns (privacy, login, admin)
```

Как в ContractSpec (paper §5): YAML декларативный, **не Turing-complete** — только named checks в `contracts/rules/`; loader отклоняет unknown `check`.

### `crawl.contract.yaml`

```yaml
mode: crawl
version: "1.0"
source: "arXiv:2602.22302 ABC-lite"

preconditions:
  - id: valid_start_url
    check: url_scheme
    allowed: [http, https]
  - id: task_present
    check: non_empty
    field: task
  - id: browser_ready
    check: browser_session_active

invariants:
  hard:
    - id: same_domain
      check: url_in_allowed_domains
    - id: url_in_candidate_queue        # I-H6: links ∪ slug probes ∪ sitemap
      check: url_in_candidate_queue
      except: [start_url]
    - id: no_private_network            # I-H8: SSRF guard
      check: public_http_url
      forbidden: [loopback, rfc1918, link_local, dot_local]
      override_flag: allow_private
    - id: redirect_recheck              # I-H9: final URL after goto
      check: post_navigation_domain
      on_violation: discard_snapshot
    - id: no_submit
      check: action_not_in
      forbidden: [submit, fill_form, click_submit]
    - id: click_destructive_handoff       # I-H12 (doc 25 Tier 3) — ДО click_safety
      check: click_not_destructive
      destructive_signals: [buy, pay, purchase, checkout, "place order", ...]
    - id: click_safety                    # I-H10 (doc 25 Tier 1)
      check: click_target_safe
      index_in: snapshot.interactive_elements
      forbidden_kinds: [submit, password]   # submit/login → Tier 2 (attended)
    - id: no_auth
      check: not_login_wall_action
  soft:
    - id: legal_pages_policy
      check: intent_conditional_paths
      avoid_by_default: crawl_forbidden.txt
      boost_when_intent: contact
      boost_paths: contact_legal   # from path_hints.yaml

governance:
  hard:
    - id: max_pages
      owner: orchestrator          # NOT enforcer-only — dual enforcement
    - id: max_depth
      owner: orchestrator
    - id: rate_limit_ms
      min_delay: 1000
    - id: robots_txt
      check: robots_allowed
    - id: page_timeout_ms
      max: 30000
  soft:
    - id: prefer_task_keywords
      owner: link_scorer

recovery:
  max_replan_per_step: 2
  fallback: link_scorer
  on_blocked: stop_status_blocked
  on_exhausted: stop_status_partial
```

### `synthesis.contract.yaml`

```yaml
mode: synthesis
version: "1.0"

preconditions:
  - id: snapshots_exist
    check: min_snapshots
    min: 1

invariants:
  hard:
    - id: valid_schema
      check: pydantic_model
      model: ExtractionResult
    - id: high_needs_quote
      check: confidence_evidence
      level: high
    - id: quote_in_snapshot
      check: evidence_substring
      fuzzy: 0.85
    - id: thinking_stripped
      check: strip_thinking_nonempty

governance:
  hard:
    - id: not_found_when_missing
      check: prefer_not_found_over_empty
    - id: max_facts
      max: 20

recovery:
  max_retries: 1
  fallback: qwen_json_extract
```

### `vision.contract.yaml`

```yaml
mode: vision
version: "1.0"

preconditions:
  - id: artifacts_or_skip
    check: min_screenshots_or_never
  - id: browser_closed
    check: orchestrator_state
    state: VISION_BATCH

invariants:
  hard:
    - id: path_in_snapshot
      check: screenshot_path_allowlist
    - id: no_traversal
      check: path_normalize_safe
    - id: max_png_bytes
      max: 5242880
    - id: valid_profile
      allowed: [desktop, tablet, mobile]

governance:
  hard:
    - id: max_vision_pages
      owner: orchestrator
    - id: max_vision_calls
      max: 12
    - id: vlm_timeout_ms
      max: 45000

recovery:
  max_retries_per_call: 1
  on_oom: skip_remaining_batch
```

### `crawl_forbidden.txt` (path substrings)

```text
/login
/signin
/signup
/register
/cart
/checkout
/privacy
/terms
/cookie
/legal
/wp-admin
```

---

## Module layout (planned)

```
backend/app/
├── contracts/
│   ├── loader.py           # YAML → Contract; reject unknown checks
│   ├── enforcer.py         # validate(action, context) → OK | Violation
│   ├── rules/              # one check ≈ one module
│   │   ├── domains.py
│   │   ├── url_in_links.py
│   │   └── robots.py
│   └── recovery.py         # replan hints, fallback triggers
├── extraction/
│   └── synthesis_validator.py
└── orchestrator/
    └── loop.py               # owns G-H1..H3 counters
```

**Integration point:** `enforcer.validate(action, context) → ValidatedAction | RecoveryAction`

---

## Drift detection (Phase 2 — lightweight)

Paper Def. 3.12: D(t) = compliance-gap + JSD. Берём **только compliance-gap** (violation rate в rolling window):

| Signal | Action |
|--------|--------|
| Hard violations ≥ **3** in one run | Log warning; navigation `temperature` 0.4 → 0.2 |
| Same I-H6 (fabricated URL) ≥ **2** | Inject stricter system reminder + shrink link list to top 5 |
| Recovery success < **50%** per run | Fallback-only navigation (link_scorer only) до конца run |
| Violations rise in **second half** of run (steps 6–10) | Paper E2 pattern — auto-tighten at step 5 |

Post-MVP: export violation CSV; optional JSD over `{navigate, stop, extract}` action types.

---

## Requirements mapping

| Requirement | Contract |
|-------------|----------|
| FR-1.4 same-domain default | I-H1 |
| FR-1.5 rate limit | G-H4 |
| FR-1.8 login walls | I-H3 + blocker detect |
| FR-1.9 CAPTCHA — no bypass | blocked status, no recovery |
| FR-2.2 evidence | S-H2, S-H3 |
| FR-2.4 not_found | S-G1 |
| FR-4.1 enforcer before execution | Runtime pipeline |
| FR-4.2 no form submit | I-H2 |
| FR-4.4 limits by orchestrator | G-H1, G-H2 + orchestrator owner |
| FR-7.3 Tier 1 click (safe interaction) | I-H7 (+click), I-H10 |
| FR-7.4 Tier 2 submit/login (confirm) | I-H2 reject autonomous + attended (doc 24) |
| FR-7.4 Tier 2 fill (текстовые поля) | I-H11 |
| FR-7.5 Tier 3 destructive (handoff) | I-H12 + attended `handoff_action` (doc 25) |

---

## MVP scope

| Item | Phase |
|------|-------|
| Hard checks I-H1, I-H6, G-H1–H3 in orchestrator | 1 (minimal) |
| Full `crawl.contract.yaml` + enforcer | 2 |
| Recovery: 2 replan + link_scorer | 2 |
| Violation logging | 2 |
| `synthesis.contract.yaml` + evidence verifier | 2 |
| **`vision.contract.yaml` + VisionLoader shield** | 2 |
| Drift auto-tighten | 2 |
| Full AgentAssert / ContractSpec parser | Post-MVP |
| JSD drift component | Post-MVP |

---

## Связанные документы

- [04-crawl-orchestrator.md](04-crawl-orchestrator.md) — state machine, link scorer
- [05-extraction-schema.md](05-extraction-schema.md) — ExtractionResult
- [Voice Interview Coach doc 13](../../voice-interview-coach/docs/13-behavioral-contracts.md) — тот же ABC-lite паттерн (enforcer перед side-effect)
- Paper PDF: `/Users/anthony/Documents/2602.22302v1.pdf`

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | v0.1 initial crawl behavioral contracts |
| 2026-07-05 | **v0.2:** ABC (arXiv:2602.22302) зафиксирован как источник правды для контроля модели; action-level shield; ContractSpec YAML; synthesis contract; drift detection; recovery table; violation schema; requirements mapping |
| 2026-07-05 | **v0.3:** I-S2 legal pages — boost when intent=contact (SEOLB); cross-ref doc 21 |
| 2026-07-05 | **v0.4:** Vision batch contract (V-H*, S-H3b/S-H6); vision.contract.yaml |
| 2026-07-05 | **v0.5 (review):** I-H6 согласован с CandidateQueue (slug probes/sitemap — конфликт с doc 21 устранён); **I-H8** private-network/SSRF guard; **I-H9** post-redirect re-check; S-H5 → Ollama `think` param (strip_thinking = fallback); cookie-banner dismissal вне ABC (orchestrator-owned, D-11) |
| 2026-07-05 | **v0.6 (review-2):** G-H2 = hop depth (D-13); I-H9 исключение step 0 (landing domain); S-H3 — in-memory проверка при synthesis (работает с --no-artifacts) |
| 2026-07-18 | **v0.7 (Phase 2 impl):** ContractEnforcer реализован (`contracts/{loader,enforcer,context,rules/}`), YAML-файлы в `data/contracts/` созданы. Уточнения: (1) правила получили поле `code` (constraint_id для violation log); (2) порядок hard-проверок фиксирован приоритетом кодов — G-H1 первым (budget → force stop, не replan); (3) G-H4 rate floor и G-H6 timeout — enforcement by construction (clamp через `effective_rate_ms`/`effective_timeout_ms`, private hosts exempt для fixtures), не reject; (4) drift auto-tighten реализован: hard ≥3 → temp 0.2, I-H6 ≥2 → top-5, recovery <50% (≥2 попыток) → fallback-only; правило «second half» покрыто пороговым hard ≥3; (5) I-H9 остался orchestrator-owned (`guards.check_redirect`), per-action guards Phase 1 переехали в `rules/` |
| 2026-07-18 | **v0.7.1 (по итогам exit-бенчмарка):** (1) **S-H3b enforcement уточнён** — quote-проверка против DOM применяется только к `source: dom`-evidence; цитата, не найденная в DOM, но совпадающая с vision_insights страницы (token_set_ratio ≥ 0.85 — устойчив к вставкам слов, в отличие от verbatim partial_ratio S-H3a), **переклассифицируется** в `source: vision` вместо удаления факта (маленькие модели нестабильно ставят source сами; S-H6 downgrade применяется после reclass); (2) **S-H3c (новое):** факт, чей `value` содержит URL посещённой страницы, при провале всех цитат не удаляется — визит и есть evidence (`quote: ""`), confidence cap `medium`; fabricated URL (∉ visited) режется как прежде |
| 2026-07-20 | **v0.8 (Phase 6 Tier 1 click, doc 25):** I-H7 схема действий +`click`; I-H2 уточнён (submit/login reject, Tier 1 click по не-submit разрешён); **I-H10 click safety** (click по `element_index` ∈ `interactive_elements`, не submit/password → иначе Tier 2/attended); `crawl.contract.yaml` +`click_safety`; recovery +I-H10; reqmap +FR-7.3/7.4. Спайк A-1 (element referencing) закрыт |
| 2026-07-20 | **v0.8.1 (Tier 2 attended login):** I-H3 уточнён — attended: `login_wall` → пауза, человек логинится в видимом браузере сам (агент паролей не хранит/не касается); unattended-логин по-прежнему reject. `looks_like_challenge` покрывает login_wall (детерминированная пауза) |
| 2026-07-20 | **v0.8.2 (Tier 2 fill):** I-H11 fill-safety — `fill` только в текстовые поля (`element_index` ∈ interactive_elements), никогда в password (креды — человек). `crawl.contract.yaml` +`fill_safety`; enforcer `validate_fill`; reqmap +FR-7.4 fill |
| 2026-07-20 | **v0.8.3 (Tier 2 submit):** I-H10 уточнён — submit-элемент разрешён под attended-подтверждением (`ctx.attended`; `confirm_action` в ACT), без attended → reject. `ActionContext.attended` добавлен |
| 2026-07-20 | **v0.9 (Tier 3 handoff, doc 25):** **I-H12** destructive click — словарь `destructive_signals` в `crawl.contract.yaml` (`click_not_destructive`, ДО `click_safety`): unattended → reject, attended → handoff (агент не жмёт — человек сам в видимом браузере). Recovery: unattended → replan, attended → пауза-handoff. Reqmap +FR-7.5. Закрывает дыру: destructive-submit больше не проходит Tier 2 confirm |
| 2026-08-06 | **v0.10 (замер журнала, doc 26 § T-3l):** **G-H3 = `visited ∪ attempted`**. `visited` — прочитанные страницы (адрес ПОСЛЕ редиректа, на нём бюджет G-H1), `attempted` — куда ходили: запрошенные URL, уведённые редиректом, и недостижимые цели (две неудачных `goto`, offsite-редирект, robots). До правки при редиректе A → B ссылка A оставалась «непосещённой» и проходила проверку бесконечно: 4 прогона с повторами, на `sports.ru` три захода на одну страницу из восьми шагов, violations пустые. `ActionContext.attempted` добавлен; `pages_visited` по-прежнему только по `visited` (иначе алиас съедал бы страницу лимита); алиасы пишутся в `metadata.redirect_aliases` и исключаются из `unreached_urls` |

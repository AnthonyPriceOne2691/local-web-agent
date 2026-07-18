# 22 — Page Screenshots

> Local Web Agent · Design doc · **v0.4** · 2026-07-05

## Назначение

**Снимки страниц** при каждом OBSERVE — визуальный audit trail для design audit, site map, ручного просмотра и input для **vision batch** (doc 23). **Capture ≠ vision:** PNG пишется локально через Playwright; анализ скриншота моделью — отдельный pass (D-6b, Phase 2).

## Зачем

| Use case | DOM alone | + Screenshot |
|----------|-----------|--------------|
| Найти текст / email | ✅ | optional |
| Типы страниц, URL patterns | ✅ | optional |
| **Design audit** (layout, colors visually) | ⚠️ weak | ✅ |
| **Responsive** (mobile menu, breakpoints) | ❌ | ✅ **3 viewports** |
| Hero, cards, visual hierarchy | ❌ | ✅ |
| Доказательство «что видел агент» | quote | quote + image |
| SPA с пустым initial DOM | ⚠️ | ✅ after render |

---

## Viewport profiles (desktop · tablet · mobile)

Канонические профили — `data/navigation/viewports.yaml`:

| Profile | Size (CSS px) | Scale | Touch | Типичное устройство |
|---------|---------------|-------|-------|---------------------|
| **desktop** | 1440 × 900 | 1× | no | PC / laptop |
| **tablet** | 834 × 1194 | 2× | yes | iPad portrait |
| **mobile** | 390 × 844 | 3× | yes | iPhone 14 class |

Tablet/mobile включают **mobile UA** + `is_mobile` / `has_touch` где уместно — не только resize окна.

### Navigation vs screenshots

| Фаза | Viewport | Почему |
|------|----------|--------|
| **Navigate + DOM extract + LLM** | **desktop only** | Стабильная навигация, footer links видны, один snapshot для Qwen |
| **Screenshots** | 1–3 профиля | «Как выглядит на PC / планшете / телефоне» |

Агент **не** ходит по сайту три раза в трёх viewport'ах — одна загрузка URL, затем смена viewport и повторный settle перед каждым PNG.

---

## Capture pipeline

```
Playwright goto + wait (desktop viewport)
        │
        ▼
Page Observer → DOM snapshot (desktop)
        │
        ▼ (if capture_screenshots enabled)
FOR each profile in screenshot_viewports:
        set_viewport_size + UA flags (viewports.yaml)
        wait 300ms (reflow / lazy layout)
        page.screenshot() → PNG
        │
        ▼
PageSnapshot.screenshots[] { profile, path, width, height, ... }
```

**Timing:** первый screenshot после основного settle; каждый доп. viewport + **~300 ms** reflow.

---

## Configuration

| Field | Default | Description |
|-------|---------|-------------|
| `capture_screenshots` | `auto` | `always` \| `never` \| `auto` |
| `screenshot_viewports` | см. ниже | `desktop` \| `desktop,tablet,mobile` \| `all` |
| `screenshot_full_page` | `false` | per profile; full scrollable page |
| `screenshot_format` | `png` | `png` only MVP |

### `screenshot_viewports` defaults

| Context | Profiles |
|---------|----------|
| `capture_screenshots: never` | — |
| `auto` + intent `information`, `generic` | `[desktop]` if screenshots on |
| `auto` + intent **`design_audit`** | **`[desktop, tablet, mobile]`** |
| `auto` + intent **`site_map`** | `[desktop]` |
| `--screenshot-viewports all` | `[desktop, tablet, mobile]` |

### `auto` mode (capture on/off)

| task_intent | Screenshots |
|-------------|-------------|
| `design_audit` | **on** + **all 3 viewports** |
| `site_map` | **on**, desktop only |
| `information`, `generic`, others | **off** |
| **любой intent + `main_text < 200`** | **force desktop PNG** («SPA fallback capture», doc 03) — иначе vision R2 (doc 23) не сработает |

Override: CLI `--screenshots`, `--no-screenshots`, `--screenshot-viewports mobile,desktop`.

---

## Playwright implementation

```python
# After DOM extract on desktop:
for profile in config.screenshot_viewports:
    vp = load_viewport(profile)  # viewports.yaml
    await page.set_viewport_size({"width": vp.width, "height": vp.height})
    # Phase 2: optional context-level UA swap via page.emulate_media or new_context per profile
    await page.wait_for_timeout(300)
    path = artifacts / f"{step:03d}_{slug}_{profile}.png"
    await page.screenshot(path=path, full_page=config.screenshot_full_page, type="png", animations="disabled", caret="hide")
# Restore desktop viewport before next navigation
await page.set_viewport_size(desktop_viewport)
```

**Phase 2 accuracy:** для `design_audit` опционально **reload per profile** (`screenshot_reload_per_viewport: true`) — если сайт отдаёт разный HTML по UA (m.example.com). Default `false` (resize only).

| Setting | Default | Why |
|---------|---------|-----|
| Navigation viewport | desktop 1440×900 | doc 03 |
| Reflow wait | 300 ms | CSS breakpoints |
| `full_page` | false | 3× full_page = huge files |
| Cookie banners | not dismissed MVP | honest capture; **см. D-11 ниже** |

> **Known limitation — `full_page` + lazy loading:** контент ниже fold с lazy-load приедет пустым (никакого скролла в MVP). Для `full_page: true` в Phase 2 — опциональный auto-scroll до capture. Viewport-only (default) не затронут.

---

## D-11: Cookie / consent banners — ✅ CLOSED (detect → hide → click)

**Проблема:** primary use case — сравнительный design audit (UC-1). На EU/GDPR-сайтах каждый скриншот будет закрыт consent-стеной → vision опишет баннер, а не дизайн. `screen_status: obstructed` (doc 23) детектирует проблему, но не решает её.

**Решение — три ступени (Phase 2), privacy-first:**

| Ступень | Что | Когда |
|---------|-----|-------|
| **0. Detect** (~50 ms) | DOM-эвристика: fixed/sticky элемент, high z-index, покрывает > 25% viewport + keywords (cookie/consent/gdpr/согласие) | Перед каждым скриншотом; ничего не найдено → ноль оверхеда |
| **1. Hide** (default) | Инъекция CSS: скрыть overlay + backdrop, снять scroll-lock (`overflow` на html/body). **Согласие никому не даётся** — трекеры не активируются; **ноль взаимодействий со страницей** | Detect сработал |
| **2. Click** (fallback) | Клик по known-CMP кнопкам (OneTrust, Cookiebot, Usercentrics, Didomi, Complianz); **reject-first** («отклонить/только необходимые»), accept — только за флагом `consent_click: accept` (consent-wall «согласись или плати»). Timeout 2 s, 1 попытка **на сайт** (context живёт весь run) | После hide detect всё ещё срабатывает |

**Phase 1 (MVP):** honest capture; `obstructed`-статистика из реальных прогонов калибрует Phase 2.

**Config:**

```yaml
consent_handling: auto      # auto (detect→hide→click-reject) | hide_only | never
consent_click: reject_first # reject_first | accept | never
```

**Селекторы:** `data/navigation/consent_selectors.yaml` — `hide_selectors` (generic + per-CMP, снапшот EasyList-Cookie-класса списков) и `click_selectors` (per-CMP reject/accept). Данные, не код (DRY, doc 18).

**Метаданные и честность:** per-page `consent_handling: none | hidden | clicked_reject | clicked_accept | failed`; vision `screen_status` — контроль результата. **UC-1 fairness:** если у сайтов сессии разный consent-статус — comparison report обязан пометить (сравнение «hero vs баннер» нечестное).

**Контракты (doc 13):** детерминированный шаг оркестратора в OBSERVE, не LLM-действие — через enforcer не проходит, I-H2 не затрагивает; default-ступень (hide) вообще не взаимодействует со страницей.

**Size budget (3 viewports, viewport-only):** ~150–250 KB × 3 ≈ **450–750 KB** per page.  
10 pages × 3 ≈ **5–7 MB**/run design audit — OK on 512 GB SSD.

**Latency:** +~0.3–0.5 s per extra viewport after first.

---

## Storage layout

```
data/runs/artifacts/{run_id}/
├── screenshots/
│   ├── 001_home_desktop.png
│   ├── 001_home_tablet.png
│   ├── 001_home_mobile.png
│   ├── 002_pricing_desktop.png
│   └── ...
├── steps/
│   └── 001.json
└── result.json
```

### Filename

```
{step_index:03d}_{slug}_{profile}.png
```

`profile` ∈ `desktop` | `tablet` | `mobile`.

### PageSnapshot field

```json
{
  "url": "https://example.com/pricing",
  "viewport_navigation": "desktop",
  "screenshots": [
    {
      "profile": "desktop",
      "relative_path": "screenshots/002_pricing_desktop.png",
      "width": 1440,
      "height": 900,
      "full_page": false,
      "bytes": 198400
    },
    {
      "profile": "tablet",
      "relative_path": "screenshots/002_pricing_tablet.png",
      "width": 834,
      "height": 1194,
      "full_page": false,
      "bytes": 142080
    },
    {
      "profile": "mobile",
      "relative_path": "screenshots/002_pricing_mobile.png",
      "width": 390,
      "height": 844,
      "full_page": false,
      "bytes": 89600
    }
  ]
}
```

If `capture_screenshots=never`: `screenshots` omitted or `[]`.

---

## API & CLI

### POST /runs

```json
{
  "capture_screenshots": "auto",
  "screenshot_viewports": ["desktop", "tablet", "mobile"],
  "screenshot_full_page": false
}
```

Preset string also allowed: `"screenshot_viewports": "all"`.

### GET /runs/{run_id}/steps/{index}/screenshot

Query: `?profile=desktop` | `tablet` | `mobile` (default `desktop`).

Returns `image/png`. 404 if profile not captured.

### CLI

```bash
agent crawl ... --screenshots
agent crawl ... --screenshot-viewports all
agent crawl ... --screenshot-viewports desktop,mobile
agent crawl ... --screenshot-full-page

agent runs show <id> --open-screenshots
```

Markdown report (doc 05): три колонки или stacked images per step для design audit.

---

## Extraction & evidence

```json
{
  "evidence": [{
    "url": "https://example.com/pricing",
    "quote": "Enterprise: Contact us",
    "screenshot_paths": {
      "desktop": "screenshots/002_pricing_desktop.png",
      "mobile": "screenshots/002_pricing_mobile.png"
    }
  }]
}
```

`design_tokens.responsive_notes` (Phase 2): «hamburger menu on mobile», «3-column → 1-column» — с привязкой к screenshot paths.

---

## Privacy & retention

- Screenshots **local only**
- `agent runs delete <id>` removes entire `artifacts/{run_id}/`
- Login forms captured on all viewports if page visited

---

## Vision analysis (Phase 2 — doc 23)

| Feature | Phase |
|---------|-------|
| PNG capture (this doc) | **1** |
| Multi-viewport (desktop/tablet/mobile) | **1** |
| Gallery in CLI / report | **2** |
| VLM analyze PNG → `vision_insights` | **2** ([doc 23](23-vision-analysis.md)) |
| VLM compares mobile vs desktop in synthesis | **2** |

---

## Testing

| Test | Type |
|------|------|
| 3 PNGs when `screenshot_viewports=all` | integration |
| desktop-only default for generic intent | unit |
| all 3 for design_audit + auto | unit |
| Filename `{slug}_{profile}.png` | unit |
| GET screenshot `?profile=mobile` | integration |
| Viewport restored to desktop after capture loop | integration |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | v0.1: page screenshot capture spec |
| 2026-07-05 | **v0.2:** multi-viewport desktop/tablet/mobile; viewports.yaml; navigation stays desktop |
| 2026-07-05 | Vision analysis phase mapping → doc 23 (Phase 2) |
| 2026-07-05 | **v0.3 (review):** D-11 cookie-banner dismissal (best_effort Phase 2, consent_selectors.yaml, вне ABC); SPA fallback capture в auto mode; full_page × lazy-load limitation |
| 2026-07-05 | **v0.4:** D-11 **CLOSED** — detect→hide→click-reject (privacy-first: default без согласия и без взаимодействия); consent_handling метаданные; UC-1 fairness rule |

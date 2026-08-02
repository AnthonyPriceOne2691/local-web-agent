"""Key pages heuristic (doc 23 § auto mode): R0 homepage · R1 priority ·
R2 empty-DOM (desktop only) · R3 design_audit все; caps 5 pages / 12 calls."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.snapshot import PageSnapshot, ScreenshotRef

SPA_TEXT_THRESHOLD = 200
VISION_TASK_KEYWORDS = (
    "look",
    "design",
    "screenshot",
    "layout",
    "color",
    "дизайн",
    "выгляд",
    "скриншот",
    "цвет",
)


@dataclass
class VisionJob:
    snapshot: PageSnapshot
    shot: ScreenshotRef


def vision_wanted(mode: str, intent: str, task: str, snapshots: list[PageSnapshot]) -> bool:
    """auto-триггеры doc 23: design_audit · пустой DOM · vision-слова в задаче."""
    if mode == "never":
        return False
    if not any(s.screenshots for s in snapshots):
        return False
    if mode == "always" or intent == "design_audit":
        return True
    if any(len(s.main_text) < SPA_TEXT_THRESHOLD for s in snapshots if s.screenshots):
        return True
    task_l = task.lower()
    return any(kw in task_l for kw in VISION_TASK_KEYWORDS)


def select_vision_jobs(
    snapshots: list[PageSnapshot],
    *,
    intent: str,
    mode: str,
    max_pages: int = 5,
    max_calls: int = 12,
) -> tuple[list[VisionJob], list[str]]:
    """(jobs, skipped_urls). Selection order doc 23: design_audit все →
    R0 homepage → R1 priority (свежие первыми) → R2 empty-DOM; хвост в skipped."""
    with_shots = [s for s in snapshots if s.screenshots]
    if not with_shots:
        return [], []

    if intent == "design_audit" or mode == "always":
        pages = list(with_shots)  # page cap не применяется (кроме max_calls)
    else:
        pages = _key_pages(snapshots, with_shots)[:max_pages]

    jobs: list[VisionJob] = []
    for snap in pages:
        for shot in _profiles_for(snap, intent):
            if len(jobs) >= max_calls:
                break
            jobs.append(VisionJob(snapshot=snap, shot=shot))

    analyzed_urls = {j.snapshot.url for j in jobs}
    skipped = [s.url for s in with_shots if s.url not in analyzed_urls]
    return jobs, skipped


def _key_pages(snapshots: list[PageSnapshot], with_shots: list[PageSnapshot]) -> list[PageSnapshot]:
    """Ключевые страницы в порядке doc 23: R0 homepage → R1 priority → R2 empty-DOM.

    Порядок содержателен, а не декоративен: он решает, кого VLM успеет посмотреть
    до потолка вызовов, а кто уйдёт в skipped.
    """
    ordered: list[PageSnapshot] = []
    if snapshots and snapshots[0].screenshots:  # R0 homepage
        ordered.append(snapshots[0])
    for s in reversed(with_shots):  # R1 priority — most recent first
        if s.priority and s not in ordered:
            ordered.append(s)
    for s in with_shots:  # R2 empty DOM
        if len(s.main_text) < SPA_TEXT_THRESHOLD and s not in ordered:
            ordered.append(s)
    return ordered


def _profiles_for(snap: PageSnapshot, intent: str) -> list[ScreenshotRef]:
    if intent == "design_audit":
        return list(snap.screenshots)  # все captured профили
    if len(snap.main_text) < SPA_TEXT_THRESHOLD:  # R2: desktop only
        return [s for s in snap.screenshots if s.profile == "desktop"][:1]
    wanted = [s for s in snap.screenshots if s.profile in ("desktop", "mobile")]
    return wanted or list(snap.screenshots)[:1]

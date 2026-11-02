"""블로그 초안(마크다운)과 캘린더(.ics) 생성."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .core import KIND_LABEL, Event, fmt_dt, now_kst

DISCLAIMER = (
    "> ⚠️ 이벤트 조건·기한은 플랫폼 사정에 따라 예고 없이 바뀌거나 예산 소진 시 조기 종료될 수 있어요. "
    "참여 전 앱 내 공지를 한 번 더 확인하세요. 문자·DM으로 온 '혜택 링크'는 누르지 말고 앱에서 직접 들어가는 게 안전합니다."
)


def _bullets(items: list[str], empty: str = "") -> str:
    if not items:
        return empty
    return "\n".join(f"- {x}" for x in items)


def _link_line(ev: Event) -> str:
    v = ev.link_check()
    if v.level == "official":
        return f"[{ev.label()} 공식 이벤트 페이지]({ev.url})"
    if v.level == "none":
        return "앱 내 메뉴에서 직접 진입"
    # 공식 확인이 안 된 링크는 본문에 하이퍼링크로 싣지 않는다
    return f"(링크 미게재 — {v.reason})"


def schedule_rows(ev: Event, now: datetime | None = None) -> list[tuple[str, str]]:
    """참여 일정표: (언제, 할 일)."""
    now = now or now_kst()
    rows: list[tuple[str, str]] = []
    if ev.start_dt and ev.start_dt > now:
        rows.append((fmt_dt(ev.start_dt), "이벤트 오픈 — " + ("선착순이라 오픈 직후 참여 권장" if ev.first_come else "참여 시작")))
    else:
        rows.append(("지금 바로", "선착순·예산 소진형이라 오늘 참여 권장" if ev.first_come else "참여 가능"))
    if ev.end_dt:
        remind = (ev.end_dt - timedelta(days=1)).replace(hour=20, minute=0)
        if remind > now:
            rows.append((fmt_dt(remind), "리마인드 — 아직 안 했다면 오늘 처리"))
        rows.append((fmt_dt(ev.end_dt), "마감"))
    return rows


def render_post(ev: Event, now: datetime | None = None) -> str:
    now = now or now_kst()
    kind = KIND_LABEL.get(ev.kind, ev.kind)
    effort = f"약 {ev.effort_min}분" if ev.effort_min else "확인 필요"
    title = f"[{ev.dday(now)}] {ev.label()} {ev.title} — 참여 방법·마감·꿀팁 정리"
    table = "\n".join(f"| {when} | {what} |" for when, what in schedule_rows(ev, now))
    warn_unverified = (
        "" if ev.verified else
        "\n> 🔎 **[편집 메모 — 발행 전 삭제]** 아직 공식 공지/앱 화면으로 검증되지 않은 이벤트입니다. 발행 전 반드시 확인하세요.\n"
    )
    cautions = list(ev.cautions)
    if ev.first_come:
        cautions.insert(0, "선착순/예산 소진 시 조기 종료될 수 있음")
    return f"""# {title}
{warn_unverified}
## 한눈에 보기

| 항목 | 내용 |
|---|---|
| 플랫폼 | {ev.label()} |
| 유형 | {kind} |
| 혜택 | {ev.reward or '확인 필요'} |
| 기간 | {fmt_dt(ev.start_dt) if ev.start_dt else '진행 중'} ~ {fmt_dt(ev.end_dt)} |
| 남은 기간 | **{ev.dday(now)}** ({ev.status(now)}) |
| 소요 시간 | {effort} |
| 참여 경로 | {_link_line(ev)} |

## 참여 방법

{chr(10).join(f"{i}. {s}" for i, s in enumerate(ev.steps, 1)) or "1. (취재 후 채울 것)"}

## 꿀팁

{_bullets(ev.tips, "- (취재 후 채울 것)")}

## 주의할 점

{_bullets(cautions, "- 특이사항 없음")}

## 일정 (캘린더에 넣어두세요)

| 언제 | 할 일 |
|---|---|
{table}

{DISCLAIMER}

<sub>출처: {', '.join(ev.sources) if ev.sources else '취재 필요'} · 최초 감지 {ev.detected_at}</sub>
"""


def render_roundup(events: list[Event], now: datetime | None = None, title: str | None = None) -> str:
    now = now or now_kst()
    title = title or f"{now:%m월 %d일} 기준 놓치면 아까운 앱테크 이벤트 {len(events)}개 (마감 임박순)"
    lines = [f"# {title}", "", "## 마감 임박순 요약", "",
             "| 남은 기간 | 플랫폼 | 이벤트 | 혜택 | 마감 | 소요 |", "|---|---|---|---|---|---|"]
    for e in events:
        flag = " 🔥" if e.status(now) == "임박" else (" ⏳" if e.status(now) == "예정" else "")
        lines.append(f"| **{e.dday(now)}**{flag} | {e.label()} | {e.title}{' (선착순)' if e.first_come else ''} | "
                     f"{e.reward or '-'} | {fmt_dt(e.end_dt)} | {f'{e.effort_min}분' if e.effort_min else '-'} |")
    lines.append("")
    for e in events:
        lines += [f"## {e.label()} — {e.title} ({e.dday(now)})", "",
                  f"- 혜택: {e.reward or '확인 필요'}",
                  f"- 기간: {fmt_dt(e.start_dt) if e.start_dt else '진행 중'} ~ {fmt_dt(e.end_dt)}",
                  f"- 참여 경로: {_link_line(e)}"]
        if e.steps:
            lines.append("- 방법: " + " → ".join(e.steps))
        for t in e.tips:
            lines.append(f"- 💡 {t}")
        for c in ([("선착순/예산 소진 시 조기 종료")] if e.first_come else []) + e.cautions:
            lines.append(f"- ⚠️ {c}")
        if not e.verified:
            lines.append("- 🔎 [편집 메모 — 발행 전 삭제] 미검증 이벤트")
        lines.append("")
    lines += [DISCLAIMER, ""]
    return "\n".join(lines)


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def render_ics(events: list[Event], now: datetime | None = None) -> str:
    """마감 1시간짜리 일정 + 하루 전/3시간 전 알림. 시작 전 이벤트는 오픈 알림도 추가."""
    now = now or now_kst()
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//event-radar//KO", "CALSCALE:GREGORIAN",
           "X-WR-CALNAME:앱테크 이벤트 마감"]
    stamp = _ics_dt(now)
    for e in events:
        if not e.end_dt:
            continue
        desc = _ics_escape(f"{e.reward}\n" + "\n".join(e.steps) + (f"\n{e.url}" if e.link_check().level == "official" else ""))
        out += ["BEGIN:VEVENT", f"UID:{e.id}-end@event-radar", f"DTSTAMP:{stamp}",
                f"DTSTART:{_ics_dt(e.end_dt - timedelta(hours=1))}", f"DTEND:{_ics_dt(e.end_dt)}",
                f"SUMMARY:{_ics_escape(f'[마감] {e.label()} {e.title}')}", f"DESCRIPTION:{desc}"]
        for trig, msg in (("-P1D", "내일 마감"), ("-PT3H", "곧 마감")):
            out += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER;RELATED=END:{trig}", f"DESCRIPTION:{_ics_escape(msg)}", "END:VALARM"]
        out.append("END:VEVENT")
        if e.start_dt and e.start_dt > now:
            out += ["BEGIN:VEVENT", f"UID:{e.id}-start@event-radar", f"DTSTAMP:{stamp}",
                    f"DTSTART:{_ics_dt(e.start_dt)}", f"DTEND:{_ics_dt(e.start_dt + timedelta(minutes=30))}",
                    f"SUMMARY:{_ics_escape(f'[오픈] {e.label()} {e.title}')}",
                    "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT10M", "DESCRIPTION:곧 오픈", "END:VALARM",
                    "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"

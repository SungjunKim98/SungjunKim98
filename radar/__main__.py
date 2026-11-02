"""사용법: python -m radar <명령> ...

  add      이벤트 추가/갱신 (--json 파일 또는 인자)
  list     진행중·임박·예정 이벤트를 마감순으로 표시
  check    링크가 공식 도메인인지 검사 (스미싱 필터)
  post     이벤트 1건 블로그 초안 생성
  roundup  진행중 이벤트 모음 글 생성
  ics      마감/오픈 알림 캘린더(.ics) 생성
  prune    마감된 이벤트를 archive 파일로 이동
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .core import Event, Store, check_link, fmt_dt, now_kst
from .render import render_ics, render_post, render_roundup

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "events.json"


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"→ {out}")
    else:
        sys.stdout.write(text)


def cmd_add(a, store: Store) -> int:
    if a.json:
        raw = json.loads(Path(a.json).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
    else:
        if not (a.platform and a.title):
            print("--platform 과 --title 은 필수", file=sys.stderr)
            return 2
        items = [{k: v for k, v in dict(
            platform=a.platform, title=a.title, kind=a.kind, url=a.url or "", start=a.start, end=a.end,
            reward=a.reward or "", effort_min=a.effort, steps=a.step or [], tips=a.tip or [],
            cautions=a.caution or [], sources=a.source or [], first_come=a.first_come, verified=a.verified,
        ).items() if v is not None}]
    for item in items:
        ev, new = store.upsert(Event(**item))
        v = ev.link_check()
        print(f"{'NEW ' if new else 'UPD '} {ev.id}  {ev.label()} {ev.title}  [{ev.dday()}]  link={v.level}")
        if v.level in ("suspicious", "shortener"):
            print(f"      ⚠️  {v.reason}")
    store.save()
    return 0


def cmd_list(a, store: Store) -> int:
    evs = store.events if a.all else store.active(include_upcoming=True)
    if a.json:
        print(json.dumps([asdict(e) | {"status": e.status(), "dday": e.dday()} for e in evs], ensure_ascii=False, indent=2))
        return 0
    if not evs:
        print("(진행 중인 이벤트 없음)")
    for e in evs:
        mark = {"임박": "🔥", "예정": "⏳", "마감": "✖"}.get(e.status(), "  ")
        ver = "" if e.verified else " (미검증)"
        print(f"{mark} {e.dday():>7}  {e.id}  {e.label():<5} {e.title}  ~{fmt_dt(e.end_dt)}  {e.reward}{ver}")
    return 0


def cmd_check(a, _store) -> int:
    worst = 0
    for url in a.urls:
        v = check_link(url, a.platform)
        icon = {"official": "✅", "unknown": "❔", "shortener": "⚠️ ", "suspicious": "🚨", "none": "-"}[v.level]
        print(f"{icon} {v.level:<10} {url}\n   {v.reason}")
        worst = max(worst, {"official": 0, "none": 0, "unknown": 1, "shortener": 1, "suspicious": 2}[v.level])
    return worst


def cmd_post(a, store: Store) -> int:
    ev = store.get(a.id)
    _write(render_post(ev), a.out)
    return 0


def cmd_roundup(a, store: Store) -> int:
    evs = store.active(include_upcoming=not a.no_upcoming)
    if a.platform:
        evs = [e for e in evs if e.platform == a.platform]
    _write(render_roundup(evs, title=a.title), a.out)
    return 0


def cmd_ics(a, store: Store) -> int:
    _write(render_ics(store.active()), a.out)
    return 0


def cmd_prune(a, store: Store) -> int:
    now = now_kst()
    done = [e for e in store.events if e.status(now) == "마감"]
    if not done:
        print("마감된 이벤트 없음")
        return 0
    arch = Store(store.path.with_name("archive.json"))
    for e in done:
        arch.upsert(e)
    arch.save()
    store.events = [e for e in store.events if e not in done]
    store.save()
    print(f"{len(done)}건 → {arch.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="앱테크 일회성 이벤트 레이더")
    p.add_argument("--db", default=str(DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add")
    s.add_argument("--json", help="이벤트 JSON(객체 또는 배열) 파일")
    s.add_argument("--platform"); s.add_argument("--title"); s.add_argument("--kind", default="etc")
    s.add_argument("--url"); s.add_argument("--start"); s.add_argument("--end"); s.add_argument("--reward")
    s.add_argument("--effort", type=int, help="소요 시간(분)")
    for f in ("step", "tip", "caution", "source"):
        s.add_argument(f"--{f}", action="append")
    s.add_argument("--first-come", action="store_true"); s.add_argument("--verified", action="store_true")

    s = sub.add_parser("list"); s.add_argument("--all", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("check"); s.add_argument("urls", nargs="+"); s.add_argument("--platform")
    s = sub.add_parser("post"); s.add_argument("id"); s.add_argument("--out")
    s = sub.add_parser("roundup"); s.add_argument("--out"); s.add_argument("--title"); s.add_argument("--platform")
    s.add_argument("--no-upcoming", action="store_true")
    s = sub.add_parser("ics"); s.add_argument("--out")
    sub.add_parser("prune")

    a = p.parse_args(argv)
    store = Store(Path(a.db))
    return globals()[f"cmd_{a.cmd}"](a, store)


if __name__ == "__main__":
    raise SystemExit(main())

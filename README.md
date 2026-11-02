# 앱테크 이벤트 레이더

토스·카카오페이·네이버페이 등에서 뿌리는 **일회성 마케팅 이벤트**(행운퀴즈, 링크 공유, 선착순 포인트, 캐시백)를
조기에 감지해서 마감순으로 정리하고, 꿀팁·기한·일정이 들어간 블로그 초안과 캘린더(.ics)를 만드는 도구.

- `skills/event-radar/SKILL.md` — Claude가 따라 하는 감지→검증→저장→글 생성 절차 (검색 쿼리, 검증 원칙, 글 패턴)
- `radar/` — 데이터 관리·렌더링 CLI (파이썬 3.11+, 표준 라이브러리만)
- `data/events.json` — 현재 추적 중인 이벤트, `data/example-events.json` — 스키마 예시(가짜 데이터)

## 빠른 시작

```bash
python -m radar add --json data/example-events.json   # 이벤트 등록 (중복 자동 제거)
python -m radar list                                  # 🔥 48시간 내 마감 / ⏳ 오픈 예정
python -m radar check https://toss-event.co.kr/gift   # 공식 도메인 검사 (스미싱 필터)
python -m radar post <id> --out out/post.md           # 이벤트 1건 정리 글 초안
python -m radar roundup --out out/roundup.md          # 마감 임박순 모음 글 초안
python -m radar ics --out out/events.ics              # 마감 하루 전·3시간 전 알림 캘린더
python -m radar prune                                 # 마감된 건 archive.json으로
```

수동 등록 예:

```bash
python -m radar add --platform toss --title "만보기 2배 이벤트" --kind attendance \
  --url https://toss.im/... --end "2026-11-15 23:59" --reward "포인트 2배" --effort 1 \
  --step "토스 → 혜택 → 만보기" --tip "알림 켜두면 자정 리셋 안 놓침" --source https://... --first-come
```

## 안전장치

- 공식 도메인이 아닌 링크(범용 단축 URL, 브랜드명 흉내 도메인, http)는 초안에 하이퍼링크로 넣지 않는다
- 미검증 이벤트는 초안에 `[편집 메모 — 발행 전 삭제]` 표시가 붙는다
- 선착순/예산 소진형은 일정표가 "오늘 참여 권장"으로 바뀐다

테스트: `python -m unittest discover -s tests -t .`

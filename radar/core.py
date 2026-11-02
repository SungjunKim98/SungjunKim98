"""앱테크 이벤트 레이더 핵심 로직 (표준 라이브러리만 사용).

토스/카카오페이/네이버페이 등에서 뿌리는 일회성 마케팅 이벤트(행운퀴즈, 링크 공유,
캐시백, 선착순 혜택 등)를 한 곳에 모아 마감 임박 순으로 정리하고, 블로그 글 초안과
캘린더(.ics)를 만들어 준다.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

KST = timezone(timedelta(hours=9), "KST")

# 플랫폼별 공식 도메인. 여기 없는 도메인으로 온 "혜택 링크"는 스미싱 의심 대상.
OFFICIAL_DOMAINS: dict[str, list[str]] = {
    "toss": ["toss.im", "tossbank.com", "tosspayments.com", "tossinvest.com", "toss.oqupie.com"],
    "kakaopay": ["kakaopay.com", "kakaopaysec.com", "kakaopayins.com", "kakao.com", "kakaocorp.com"],
    "naverpay": ["naver.com", "naver.me", "pay.naver.com"],
    "kakaobank": ["kakaobank.com"],
    "payco": ["payco.com"],
    "kbank": ["kbanknow.com"],
}
# 공식 앱이 실제로 쓰는 단축/딥링크 도메인
OFFICIAL_SHORTLINKS = {"toss.im": "toss", "link.kakaopay.com": "kakaopay", "naver.me": "naverpay"}
# 출처가 불분명해지는 범용 단축 URL
GENERIC_SHORTENERS = {"bit.ly", "han.gl", "me2.do", "url.kr", "vo.la", "t.ly", "tinyurl.com", "buly.kr", "c11.kr"}

PLATFORM_LABEL = {
    "toss": "토스", "kakaopay": "카카오페이", "naverpay": "네이버페이",
    "kakaobank": "카카오뱅크", "payco": "페이코", "kbank": "케이뱅크", "etc": "기타",
}
KIND_LABEL = {
    "quiz": "퀴즈/정답 입력", "link": "링크 공유·초대", "cashback": "결제 캐시백",
    "signup": "가입·계좌개설", "attendance": "출석·미션", "coupon": "쿠폰·포인트 지급",
    "lottery": "응모·추첨", "etc": "기타",
}


def now_kst() -> datetime:
    return datetime.now(KST)


def parse_dt(value: str | None, end_of_day: bool = True) -> datetime | None:
    """'2026-11-05', '2026-11-05 23:59', ISO 문자열 모두 허용. 시간대 없으면 KST."""
    if not value:
        return None
    v = value.strip()
    dt = datetime.fromisoformat(v)
    if end_of_day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        # 날짜만 주어진 마감일은 그날 23:59로 본다
        dt = dt.replace(hour=23, minute=59)
    return dt.astimezone(KST) if dt.tzinfo else dt.replace(tzinfo=KST)


def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "미정"
    wd = "월화수목금토일"[dt.weekday()]
    return f"{dt:%m/%d}({wd}) {dt:%H:%M}"


@dataclass
class Event:
    platform: str
    title: str
    kind: str = "etc"
    url: str = ""
    start: str | None = None
    end: str | None = None
    reward: str = ""
    effort_min: int | None = None  # 예상 소요 시간(분)
    steps: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    first_come: bool = False  # 선착순/예산 소진 시 조기 종료
    verified: bool = False  # 공식 공지/앱 화면으로 확인했는지
    detected_at: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        self.platform = self.platform.lower()
        if not self.id:
            self.id = make_id(self.platform, self.title, self.url)
        if not self.detected_at:
            self.detected_at = now_kst().strftime("%Y-%m-%d %H:%M")

    # --- 시간 관련 ---
    @property
    def start_dt(self) -> datetime | None:
        return parse_dt(self.start, end_of_day=False)

    @property
    def end_dt(self) -> datetime | None:
        return parse_dt(self.end)

    def status(self, now: datetime | None = None) -> str:
        now = now or now_kst()
        if self.start_dt and now < self.start_dt:
            return "예정"
        if self.end_dt and now > self.end_dt:
            return "마감"
        if self.end_dt and self.end_dt - now <= timedelta(hours=48):
            return "임박"
        return "진행중"

    def dday(self, now: datetime | None = None) -> str:
        now = now or now_kst()
        if not self.end_dt:
            return "상시/미정"
        days = (self.end_dt.date() - now.date()).days
        if days < 0:
            return "종료"
        return "D-DAY" if days == 0 else f"D-{days}"

    def label(self) -> str:
        return PLATFORM_LABEL.get(self.platform, self.platform)

    def link_check(self) -> "LinkVerdict":
        return check_link(self.url, self.platform)


def make_id(platform: str, title: str, url: str) -> str:
    norm = re.sub(r"\s+", "", f"{platform}|{title}".lower())
    key = norm + "|" + canonical_url(url)
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def canonical_url(url: str) -> str:
    """추적용 파라미터를 제거해 같은 이벤트 링크를 중복으로 잡지 않게 한다."""
    if not url:
        return ""
    p = urlparse(url)
    drop = re.compile(r"^(utm_|fbclid|gclid|ref|share|referrer)", re.I)
    q = "&".join(kv for kv in p.query.split("&") if kv and not drop.match(kv.split("=")[0]))
    return f"{p.netloc.lower()}{p.path.rstrip('/')}" + (f"?{q}" if q else "")


@dataclass
class LinkVerdict:
    level: str  # official / shortener / unknown / suspicious / none
    reason: str


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def check_link(url: str, platform: str | None = None) -> LinkVerdict:
    if not url:
        return LinkVerdict("none", "링크 없음 — 앱 내 메뉴 경로로 안내할 것")
    p = urlparse(url if "://" in url else "https://" + url)
    host = (p.hostname or "").lower()
    if p.scheme not in ("https", "supertoss", "kakaotalk", "kakaopay", "naversearchapp"):
        return LinkVerdict("suspicious", f"https가 아닌 링크({p.scheme})")
    if host in GENERIC_SHORTENERS:
        return LinkVerdict("shortener", f"범용 단축 URL({host}) — 원본 주소 확인 전 블로그에 그대로 싣지 말 것")
    owners = [pf for pf, ds in OFFICIAL_DOMAINS.items() if any(_host_matches(host, d) for d in ds)]
    if owners:
        if platform and platform not in owners and platform != "etc":
            return LinkVerdict("suspicious", f"{host}는 {PLATFORM_LABEL.get(owners[0])} 도메인인데 플랫폼은 {platform}")
        return LinkVerdict("official", f"공식 도메인({host})")
    # 공식 브랜드명을 흉내 낸 도메인 (예: toss-event.co, kakaopay-gift.net)
    if re.search(r"(toss|kakao|naver|payco)", host):
        return LinkVerdict("suspicious", f"브랜드명을 포함한 비공식 도메인({host}) — 피싱 가능성")
    return LinkVerdict("unknown", f"공식 목록에 없는 도메인({host}) — 제휴사 페이지인지 확인 필요")


# --- 저장소 ---
class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.events: list[Event] = []
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            self.events = [Event(**e) for e in raw]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(e) for e in self.events]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def get(self, event_id: str) -> Event:
        for e in self.events:
            if e.id == event_id or e.id.startswith(event_id):
                return e
        raise KeyError(event_id)

    def upsert(self, ev: Event) -> tuple[Event, bool]:
        """같은 id면 비어있지 않은 필드만 덮어쓴다. (이벤트, 신규여부) 반환."""
        for i, old in enumerate(self.events):
            if old.id == ev.id:
                merged = asdict(old)
                for k, v in asdict(ev).items():
                    if k in ("id", "detected_at"):
                        continue
                    if v not in (None, "", [], False):
                        merged[k] = v
                self.events[i] = Event(**merged)
                return self.events[i], False
        self.events.append(ev)
        return ev, True

    def active(self, now: datetime | None = None, include_upcoming: bool = True) -> list[Event]:
        now = now or now_kst()
        keep = {"진행중", "임박"} | ({"예정"} if include_upcoming else set())
        evs = [e for e in self.events if e.status(now) in keep]
        far = datetime.max.replace(tzinfo=KST)
        return sorted(evs, key=lambda e: (e.end_dt or far, e.platform))

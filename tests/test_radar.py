import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from radar.__main__ import main
from radar.core import KST, Event, Store, canonical_url, check_link, parse_dt
from radar.render import render_ics, render_post, render_roundup

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=KST)


def ev(**kw):
    base = dict(platform="toss", title="테스트 이벤트", url="https://toss.im/e/1", end="2026-11-07")
    return Event(**(base | kw))


class ParseTest(unittest.TestCase):
    def test_date_only_end_is_end_of_day(self):
        self.assertEqual(parse_dt("2026-11-07").strftime("%H:%M"), "23:59")
        self.assertEqual(parse_dt("2026-11-07", end_of_day=False).strftime("%H:%M"), "00:00")

    def test_foreign_tz_converted_to_kst(self):
        self.assertEqual(parse_dt("2026-11-07T00:00:00+00:00").hour, 9)


class StatusTest(unittest.TestCase):
    def test_statuses(self):
        self.assertEqual(ev(end="2026-11-07").status(NOW), "진행중")
        self.assertEqual(ev(end="2026-11-03 12:00").status(NOW), "임박")
        self.assertEqual(ev(end="2026-11-01").status(NOW), "마감")
        self.assertEqual(ev(start="2026-11-05", end="2026-11-09").status(NOW), "예정")

    def test_dday(self):
        self.assertEqual(ev(end="2026-11-07").dday(NOW), "D-5")
        self.assertEqual(ev(end="2026-11-02 23:00").dday(NOW), "D-DAY")
        self.assertEqual(ev(end=None).dday(NOW), "상시/미정")


class LinkTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(check_link("https://event.toss.im/x", "toss").level, "official")
        self.assertEqual(check_link("https://toss-gift.co.kr", "toss").level, "suspicious")
        self.assertEqual(check_link("https://evil-toss.im.attacker.com", "toss").level, "suspicious")
        self.assertEqual(check_link("http://toss.im", "toss").level, "suspicious")
        self.assertEqual(check_link("https://bit.ly/x", "toss").level, "shortener")
        self.assertEqual(check_link("https://shop.example.com", "toss").level, "unknown")
        self.assertEqual(check_link("https://toss.im/x", "kakaopay").level, "suspicious")

    def test_canonical_strips_tracking(self):
        self.assertEqual(canonical_url("https://Toss.im/e/1/?utm_source=a&id=3"), "toss.im/e/1?id=3")


class StoreTest(unittest.TestCase):
    def test_dedupe_and_merge(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "e.json")
            _, new1 = s.upsert(ev(url="https://toss.im/e/1?utm_source=sms"))
            _, new2 = s.upsert(ev(url="https://toss.im/e/1", reward="500원"))
            self.assertTrue(new1)
            self.assertFalse(new2)
            self.assertEqual(len(s.events), 1)
            self.assertEqual(s.events[0].reward, "500원")
            s.save()
            self.assertEqual(Store(s.path).events[0].reward, "500원")

    def test_active_sorted_by_deadline(self):
        s = Store(Path("/nonexistent/x.json"))
        s.events = [ev(title="b", end="2026-11-09"), ev(title="a", end="2026-11-03"), ev(title="old", end="2026-10-01")]
        self.assertEqual([e.title for e in s.active(NOW)], ["a", "b"])


class RenderTest(unittest.TestCase):
    def test_post_hides_unofficial_links(self):
        md = render_post(ev(url="https://bit.ly/zz"), NOW)
        self.assertNotIn("](https://bit.ly", md)
        self.assertIn("편집 메모", md)  # unverified marker

    def test_post_verified_has_no_memo(self):
        md = render_post(ev(verified=True, first_come=True), NOW)
        self.assertNotIn("편집 메모", md)
        self.assertIn("선착순", md)
        self.assertIn("D-5", md)

    def test_roundup_and_ics(self):
        evs = [ev(title="a", end="2026-11-03"), ev(title="b", start="2026-11-05", end="2026-11-09")]
        self.assertIn("앱테크 이벤트 2개", render_roundup(evs, NOW))
        ics = render_ics(evs, NOW)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 3)  # 2 deadlines + 1 opening
        self.assertIn("DTEND:20261103T145900Z", ics)


class CliTest(unittest.TestCase):
    def test_add_list_check(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "e.json")
            src = Path(__file__).resolve().parent.parent / "data" / "example-events.json"
            self.assertEqual(main(["--db", db, "add", "--json", str(src)]), 0)
            self.assertEqual(len(json.loads(Path(db).read_text())), 2)
            self.assertEqual(main(["--db", db, "check", "https://toss.im/a"]), 0)
            self.assertEqual(main(["--db", db, "check", "https://toss-gift.kr"]), 2)


if __name__ == "__main__":
    unittest.main()

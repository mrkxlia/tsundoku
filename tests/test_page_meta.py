"""page_meta の純関数と fetch_url_meta の「例外を投げない」契約のテスト(ネットワーク不使用)。"""

from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

import page_meta


class ToAsciiUrlTest(unittest.TestCase):
    def test_ascii_url_is_unchanged(self):
        url = "https://example.com/a%20b/c?x=1&y=%E3%81%82#frag"
        self.assertEqual(page_meta.to_ascii_url(url), url)

    def test_idn_host_is_punycoded(self):
        self.assertEqual(page_meta.to_ascii_url("https://日本語.jp/path"), "https://xn--wgv71a119e.jp/path")

    def test_non_ascii_path_and_query_are_percent_encoded(self):
        self.assertEqual(
            page_meta.to_ascii_url("https://example.com/記事/1?q=検索&lang=ja"),
            "https://example.com/%E8%A8%98%E4%BA%8B/1?q=%E6%A4%9C%E7%B4%A2&lang=ja",
        )

    def test_existing_escapes_are_not_double_encoded(self):
        self.assertEqual(
            page_meta.to_ascii_url("https://example.com/%E8%A8%98/新?x=%20&y=a+b"),
            "https://example.com/%E8%A8%98/%E6%96%B0?x=%20&y=a+b",
        )

    def test_port_and_ipv6_literal_are_preserved(self):
        self.assertEqual(page_meta.to_ascii_url("http://[::1]:8080/ん"), "http://[::1]:8080/%E3%82%93")
        self.assertEqual(page_meta.to_ascii_url("https://日本語.jp:8443/x"), "https://xn--wgv71a119e.jp:8443/x")

    def test_userinfo_is_kept(self):
        self.assertEqual(
            page_meta.to_ascii_url("https://user:pass@日本語.jp/ぱす"),
            "https://user:pass@xn--wgv71a119e.jp/%E3%81%B1%E3%81%99",
        )

    def test_result_is_always_ascii(self):
        self.assertTrue(page_meta.to_ascii_url("https://例え.テスト/ぱす?く=え#ふ").isascii())

    def test_malformed_iri_raises_value_error(self):
        with self.assertRaises(ValueError):
            page_meta.to_ascii_url("https://[::1/日本")  # IPv6 の括弧不整合
        with self.assertRaises(ValueError):
            page_meta.to_ascii_url("https://a..b.日本/")  # 空ラベルは IDNA 変換不能(UnicodeError)


def _fake_response(url: str, html: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
    resp = mock.MagicMock()
    resp.status = status
    resp.geturl.return_value = url
    resp.headers = {"Content-Type": content_type}
    resp.read.return_value = html.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


PUBLISHED_HTML = '<html><head><meta property="article:published_time" content="2026-08-01T09:00:00+09:00"></head></html>'


class FetchUrlMetaTest(unittest.TestCase):
    def test_non_ascii_url_is_sent_as_ascii_and_original_notation_is_returned(self):
        ascii_url = "https://xn--wgv71a119e.jp/%E8%A8%98%E4%BA%8B"
        with mock.patch("urllib.request.urlopen", return_value=_fake_response(ascii_url, PUBLISHED_HTML)) as urlopen:
            result = page_meta.fetch_url_meta("https://日本語.jp/記事")
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, ascii_url)
        self.assertEqual(req.get_header("User-agent"), "tsundoku-suggest/1.0")
        # リダイレクト無しなら呼び出し元の表記をそのまま返す(normalize_url でのキー突合を壊さない)
        self.assertEqual(result, (True, "https://日本語.jp/記事", "2026-08-01"))

    def test_redirected_final_url_is_returned(self):
        final = "https://example.com/final"
        with mock.patch("urllib.request.urlopen", return_value=_fake_response(final, PUBLISHED_HTML)):
            result = page_meta.fetch_url_meta("https://example.com/redirect-me")
        self.assertEqual(result, (True, final, "2026-08-01"))

    def test_non_html_is_reachable_without_date(self):
        url = "https://example.com/doc.pdf"
        with mock.patch("urllib.request.urlopen", return_value=_fake_response(url, "", content_type="application/pdf")):
            self.assertEqual(page_meta.fetch_url_meta(url), (True, url, ""))

    def test_transport_unicode_error_is_contained(self):
        # 修正前に本番で起きた例外そのもの(http.client の Host ヘッダ latin-1 化)が漏れないこと
        err = UnicodeEncodeError("latin-1", "x", 0, 1, "ordinal not in range(256)")
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(page_meta.fetch_url_meta("https://example.com/"), (False, "https://example.com/", ""))

    def test_http_error_and_url_error_are_contained(self):
        http_err = urllib.error.HTTPError("https://example.com/", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=http_err):
            self.assertEqual(page_meta.fetch_url_meta("https://example.com/"), (False, "https://example.com/", ""))
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("dns")):
            self.assertEqual(page_meta.fetch_url_meta("https://example.com/"), (False, "https://example.com/", ""))

    def test_malformed_urls_are_unreachable_not_exceptions(self):
        # いずれも urlopen に到達する前に ValueError 系になる(scheme 無し / IPv6 括弧不整合 / IDNA 不能)
        for url in ("example.com/no-scheme", "https://[::1/日本", "https://a..b.日本/"):
            with self.subTest(url=url), mock.patch("urllib.request.urlopen", side_effect=AssertionError("must not be called")):
                self.assertEqual(page_meta.fetch_url_meta(url), (False, url, ""))


class SanitizePublishedTest(unittest.TestCase):
    def test_valid_date_within_tolerance_is_kept(self):
        self.assertEqual(page_meta.sanitize_published("2026-08-30", "2026-08-31 10:00"), "2026-08-30")
        self.assertEqual(page_meta.sanitize_published("2026-09-02", "2026-08-31 10:00"), "2026-09-02")  # +2日まで許容

    def test_future_past_and_garbage_fall_back_to_empty(self):
        self.assertEqual(page_meta.sanitize_published("2026-09-03", "2026-08-31 10:00"), "")  # 収集日+3日は未来
        self.assertEqual(page_meta.sanitize_published("1994-12-31", "2026-08-31"), "")
        self.assertEqual(page_meta.sanitize_published("2026-13-99", "2026-08-31"), "")
        self.assertEqual(page_meta.sanitize_published("no date", "2026-08-31"), "")
        self.assertEqual(page_meta.sanitize_published("", "2026-08-31"), "")


if __name__ == "__main__":
    unittest.main()

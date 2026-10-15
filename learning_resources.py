"""Bounded resource discovery for the existing StudyWaypoint AI conversation."""

from __future__ import annotations

import datetime as dt
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import urllib.parse
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser

from tracker import TrackerError


BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SEARCH_LIMIT = 5
MAX_SEARCHES = 12
MAX_READS = 8
MAX_TOOL_ROUNDS = 6
MAX_PAGE_BYTES = 512_000
READ_TIMEOUT = 8
USER_AGENT = "StudyWaypoint/1.2 (+learning resource discovery)"
SCORE_WEIGHTS = {"relevance": .35, "source_quality": .25, "difficulty": .20,
                 "completeness": .10, "time_fit": .10}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def clean_public_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.hostname.lower() in ("localhost",) or parsed.hostname.lower().endswith(".local"):
            return None
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return None
        if parsed.port is not None and parsed.port not in (80, 443):
            return None
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
    except ValueError:
        return None


def resource_type(url, title=""):
    parsed = urllib.parse.urlsplit(url)
    host, path = (parsed.hostname or "").lower(), parsed.path.lower()
    if host == "bilibili.com" or host.endswith(".bilibili.com"):
        return "video_series" if "/list/" in path or "/medialist/" in path else "video"
    if host == "youtube.com" or host.endswith(".youtube.com") or host == "youtu.be":
        return "video_series" if "playlist" in path or "list=" in parsed.query else "video"
    if host == "leetcode.com" or host.endswith(".leetcode.com"):
        return "practice"
    if "docs." in host or "/docs/" in path or "documentation" in title.lower():
        return "official_documentation"
    if any(word in (title + " " + path).lower() for word in ("course", "课程", "教程", "curriculum")):
        return "course"
    return "article"


class SearchProviderError(TrackerError):
    def __init__(self, provider, message, code="search_provider_error"):
        self.provider = provider
        super().__init__(f"{provider}：{message}", code, 502)


class SearchProvider:
    name = ""

    def __init__(self, transport):
        self.transport = transport

    def search(self, query, count, config):
        raise NotImplementedError

    def _normalize(self, items, count):
        if not isinstance(items, list):
            raise SearchProviderError(self.name, "返回结果格式无效")
        output = []
        for item in items[:max(count * 2, count)]:
            if not isinstance(item, dict):
                continue
            url = clean_public_url(item.get("url"))
            if not url:
                continue
            title = str(item.get("title") or "").strip()[:200]
            snippet = str(item.get("description") or item.get("content") or "").strip()[:700]
            if not title:
                continue
            output.append({"title": title, "url": url, "snippet": snippet,
                           "provider": self.name, "resource_type": resource_type(url, title),
                           "retrieved_at": utc_now(), "metadata": {},
                           "verification_status": "search_result_only"})
            if len(output) >= count:
                break
        return output


class SearXNGProvider(SearchProvider):
    name = "searxng"

    def search(self, query, count, config):
        base = config.get("searxng_url")
        if not base:
            raise SearchProviderError(self.name, "未配置实例地址；请运行 SearXNG 并启用 JSON 接口", "search_not_configured")
        url = base.rstrip("/") + "/search?" + urllib.parse.urlencode(
            {"q": query[:500], "format": "json", "categories": "general"})
        try:
            data = self.transport(url, {"Accept": "application/json"}, timeout=20)
        except TrackerError as exc:
            if "返回 403" in str(exc):
                raise SearchProviderError(self.name, "JSON 接口被拒绝；请在 search.formats 中启用 json") from exc
            raise SearchProviderError(self.name, str(exc), exc.code) from exc
        if not isinstance(data, dict):
            raise SearchProviderError(self.name, "返回结果格式无效")
        return self._normalize(data.get("results"), count)


class BraveSearchProvider(SearchProvider):
    name = "brave"

    def search(self, query, count, config):
        key = config.get("search_api_key")
        if not key:
            raise SearchProviderError(self.name, "未配置 API Key", "search_not_configured")
        url = BRAVE_URL + "?" + urllib.parse.urlencode({"q": query[:500], "count": count})
        try:
            data = self.transport(url, {"Accept": "application/json", "X-Subscription-Token": key}, timeout=20)
        except TrackerError as exc:
            raise SearchProviderError(self.name, str(exc).replace(key, "[已隐藏密钥]"), exc.code) from exc
        web = data.get("web") if isinstance(data, dict) else None
        return self._normalize(web.get("results") if isinstance(web, dict) else None, count)


class SearchRouter:
    """Configuration, never model arguments, chooses the active search provider."""

    def __init__(self, config_getter, transport):
        self.config_getter = config_getter
        self.providers = {"searxng": SearXNGProvider(transport), "brave": BraveSearchProvider(transport)}
        self._slots = threading.BoundedSemaphore(3)

    @staticmethod
    def _call(provider, query, count, config, cancel):
        for attempt in range(2):
            if cancel and cancel.is_set():
                raise TrackerError("检索已取消", "cancelled", 409)
            try:
                return provider.search(query, count, config)
            except SearchProviderError as exc:
                retryable = exc.code in ("upstream_error", "upstream_network", "upstream_timeout",
                                          "upstream_http_500", "upstream_http_502",
                                          "upstream_http_503", "upstream_http_504")
                if attempt or not retryable:
                    raise

    def search(self, query, count=SEARCH_LIMIT, cancel=None):
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise TrackerError("搜索词无效")
        count = max(1, min(SEARCH_LIMIT, int(count)))
        if cancel and cancel.is_set():
            raise TrackerError("检索已取消", "cancelled", 409)
        with self._slots:
            if cancel and cancel.is_set():
                raise TrackerError("检索已取消", "cancelled", 409)
            config = self.config_getter()
            warning = None
            provider = None
            if config.get("third_party_enabled"):
                provider = self.providers["brave"] if config.get("third_party_provider", "brave") == "brave" else None
                if provider is None:
                    warning = "第三方搜索提供商不受支持，已使用 SearXNG"
                elif not config.get("search_api_key"):
                    warning = "Brave 未填写 API Key，已使用 SearXNG"
                    provider = None
            if provider:
                try:
                    return {"results": self._call(provider, query, count, config, cancel), "provider": provider.name,
                            "warning": None}
                except SearchProviderError as exc:
                    warning = str(exc) + "；已尝试回退 SearXNG"
            # Re-read before fallback so switching off third-party search takes effect on the next request.
            current = self.config_getter()
            try:
                results = self._call(self.providers["searxng"], query, count, current, cancel)
            except SearchProviderError as exc:
                raise SearchProviderError("search", (warning + "；" if warning else "") + str(exc)) from exc
            return {"results": results, "provider": "searxng", "warning": warning}

    def test_connection(self, provider):
        if provider not in self.providers:
            raise TrackerError("未知搜索服务")
        config = self.config_getter()
        if provider == "brave" and not config.get("third_party_enabled"):
            raise TrackerError("请先启用第三方搜索，再测试 Brave 连接")
        # Zero results are a valid connected response; parsing valid JSON is enough.
        self.providers[provider].search("StudyWaypoint Python tutorial", 1, config)
        return {"provider": provider, "connected": True, "tested_at": utc_now()}


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.headings = []
        self.links = []
        self.text = []
        self._tag = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag in ("title", "h1", "h2", "h3"):
            self._tag = tag
        if tag == "meta" and attrs.get("name", "").lower() == "description":
            self.description = attrs.get("content", "")[:500]
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if tag == self._tag:
            self._tag = None

    def handle_data(self, data):
        if self._skip or not data.strip():
            return
        text = " ".join(data.split())
        if self._tag == "title":
            self.title += text + " "
        elif self._tag in ("h1", "h2", "h3") and len(self.headings) < 35:
            self.headings.append(text[:200])
        if len(self.text) < 1500:
            self.text.append(text)


class WebReader:
    """Read bounded public pages, pinning checked DNS addresses through the connection."""

    def __init__(self, fetcher=None):
        self.fetcher = fetcher or self._safe_fetch
        self._robots = {}

    @staticmethod
    def _safe_fetch(url):
        current = clean_public_url(url)
        if not current:
            raise TrackerError("网页 URL 无效或指向本机/私有地址", "unsafe_url", 400)
        for _ in range(4):
            parsed = urllib.parse.urlsplit(current)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            try:
                addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                    raise TrackerError("网页 DNS 解析到非公网地址", "unsafe_url", 400)
                family, _, _, _, target = addresses[0]
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.settimeout(READ_TIMEOUT)
                try:
                    sock.connect(target)
                    if parsed.scheme == "https":
                        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
                    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
                    host = parsed.hostname if port in (80, 443) else f"{parsed.hostname}:{port}"
                    request = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {USER_AGENT}\r\n"
                               "Accept: text/html,text/plain\r\nConnection: close\r\n\r\n").encode("ascii", "backslashreplace")
                    sock.sendall(request)
                    response = http.client.HTTPResponse(sock)
                    response.begin()
                    status = response.status
                    kind = response.getheader("Content-Type", "")
                    location = response.getheader("Location")
                    length = response.getheader("Content-Length")
                    if length and int(length) > MAX_PAGE_BYTES:
                        raise TrackerError("网页超过读取大小限制", "page_too_large", 502)
                    if status in (301, 302, 303, 307, 308):
                        next_url = clean_public_url(urllib.parse.urljoin(current, location or ""))
                        if not next_url:
                            raise TrackerError("网页重定向到不安全地址", "unsafe_url", 400)
                        current = next_url
                        continue
                    if status == 404:
                        return current, status, kind, b""
                    if status != 200:
                        raise TrackerError(f"网页返回 HTTP {status}", "page_unavailable", 502)
                    if not any(label in kind.lower() for label in ("text/html", "text/plain")):
                        raise TrackerError("网页不是 HTML 或纯文本", "unsupported_page", 502)
                    data = response.read(MAX_PAGE_BYTES + 1)
                    if len(data) > MAX_PAGE_BYTES:
                        raise TrackerError("网页超过读取大小限制", "page_too_large", 502)
                    return current, status, kind, data
                finally:
                    sock.close()
            except (OSError, ValueError, http.client.HTTPException) as exc:
                raise TrackerError(f"无法读取网页：{type(exc).__name__}", "page_unavailable", 502) from exc
        raise TrackerError("网页重定向次数过多", "page_unavailable", 502)

    def _allowed(self, url):
        parsed = urllib.parse.urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            try:
                _, status, _, body = self.fetcher(origin + "/robots.txt")
                rules = RobotFileParser()
                rules.parse(body.decode("utf-8", "replace").splitlines() if status == 200 else [])
                self._robots[origin] = rules
            except TrackerError:
                self._robots[origin] = None
        rules = self._robots[origin]
        return rules is not None and rules.can_fetch(USER_AGENT, url)

    def read(self, url):
        safe = clean_public_url(url)
        if not safe:
            raise TrackerError("网页 URL 无效或指向本机/私有地址", "unsafe_url", 400)
        if not self._allowed(safe):
            raise TrackerError("网站访问规则不可确认或禁止读取", "page_unavailable", 502)
        final, _, kind, body = self.fetcher(safe)
        if not clean_public_url(final):
            raise TrackerError("网页最终地址不安全", "unsafe_url", 400)
        if "text/plain" in kind.lower():
            return {"url": final, "title": "", "description": "", "headings": [],
                    "text": body.decode("utf-8", "replace")[:6000], "links": []}
        parser = _PageParser()
        parser.feed(body.decode("utf-8", "replace"))
        links = []
        for href in parser.links[:100]:
            target = clean_public_url(urllib.parse.urljoin(final, href))
            if target and target not in links:
                links.append(target)
        return {"url": final, "title": parser.title.strip()[:200],
                "description": parser.description, "headings": parser.headings[:30],
                "text": " ".join(parser.text)[:6000], "links": links[:50]}

    def explore(self, url, max_pages=3, cancel=None):
        max_pages = max(1, min(4, int(max_pages)))
        origin = urllib.parse.urlsplit(url).hostname
        queue, visited, pages = [url], set(), []
        while queue and len(pages) < max_pages:
            if cancel and cancel.is_set():
                raise TrackerError("检索已取消", "cancelled", 409)
            target = queue.pop(0)
            if target in visited:
                continue
            visited.add(target)
            try:
                page = self.read(target)
            except TrackerError:
                continue
            pages.append(page)
            if len(pages) == 1:
                queue.extend(link for link in page["links"] if urllib.parse.urlsplit(link).hostname == origin
                             and any(word in link.lower() for word in ("course", "chapter", "tutorial", "docs", "lesson")))
        return pages


class LearningResourceAgent:
    """One bounded search worker reused by tool calls and deterministic fallback."""

    def __init__(self, router, reader=None):
        self.router = router
        self.reader = reader or WebReader()

    @staticmethod
    def _queries(layer, topic, preferences):
        topic = topic.strip()[:180]
        language = str(preferences.get("language", "")).lower()
        platform = str(preferences.get("platform", "")).lower()
        if layer == "global":
            queries = [f"{topic} 系统课程 教程", f"{topic} official documentation course",
                       f"{topic} university open course"]
        else:
            queries = [f"{topic} 官方文档 具体章节", f"{topic} tutorial practice exercise"]
        if "bilibili" in platform or "b站" in platform or "中文视频" in language:
            queries.append(f"site:bilibili.com {topic} 教程 合集")
        if "youtube" in platform or "英文视频" in language:
            queries.append(f"site:youtube.com {topic} course playlist")
        return queries[:4]

    @staticmethod
    def _score(item, topic):
        words = [word.lower() for word in re.split(r"\s+", topic) if len(word) > 1]
        text = (item["title"] + " " + item["snippet"]).lower()
        relevance = sum(word in text for word in words) / max(1, len(words))
        official = item["resource_type"] == "official_documentation"
        source_quality = 1.0 if official else .7 if item["verification_status"] == "content_verified" else .4
        completeness = .8 if item.get("metadata", {}).get("headings") else .5 if item["resource_type"] in ("course", "video_series") else .2
        difficulty = .5  # Unknown until the LLM compares the content with the learner's level.
        time_fit = .5  # Unknown when duration is not verified.
        return round(relevance * SCORE_WEIGHTS["relevance"] + source_quality * SCORE_WEIGHTS["source_quality"]
                     + difficulty * SCORE_WEIGHTS["difficulty"] + completeness * SCORE_WEIGHTS["completeness"]
                     + time_fit * SCORE_WEIGHTS["time_fit"], 3)

    def discover(self, layer, topic, preferences=None, *, cache=None, prior=None, cancel=None,
                 max_searches=4, max_reads=2, status=None):
        if layer not in ("global", "task"):
            raise TrackerError("资源检索层级无效")
        if not isinstance(topic, str) or not topic.strip() or len(topic) > 300:
            raise TrackerError("学习主题无效")
        preferences = preferences if isinstance(preferences, dict) else {}
        cache = cache if isinstance(cache, dict) else {}
        prior = prior if isinstance(prior, list) else []
        items, warnings, calls, reads = [], [], 0, 0
        topic_key = topic.strip().lower()
        if layer == "task":
            for item in prior:
                if not isinstance(item, dict):
                    continue
                text = (str(item.get("title", "")) + " " + str(item.get("snippet", ""))).lower()
                if topic_key in text and item.get("resource_type") in ("course", "official_documentation", "video_series"):
                    items.append(item)
        for query in self._queries(layer, topic, preferences):
            if cancel and cancel.is_set():
                raise TrackerError("检索已取消", "cancelled", 409)
            if calls >= max_searches or len(items) >= 15:
                break
            key = query.lower()
            config = self.router.config_getter()
            preferred = "brave" if config.get("third_party_enabled") and config.get("search_api_key") else "searxng"
            cached = cache.get(key)
            if isinstance(cached, dict) and cached.get("provider") == preferred:
                batch = cached.get("results", [])
            else:
                if status:
                    status("正在搜索系统课程" if layer == "global" else "正在查找具体学习资源")
                try:
                    response = self.router.search(query, cancel=cancel)
                except SearchProviderError as exc:
                    warnings.append(str(exc))
                    continue
                batch = response["results"]
                cache[key] = {"provider": response["provider"], "results": batch}
                while len(cache) > 80:
                    cache.pop(next(iter(cache)))
                calls += 1
                if response.get("warning"):
                    warnings.append(response["warning"])
            items.extend(batch)
        unique = {}
        for item in items:
            if isinstance(item, dict) and clean_public_url(item.get("url")):
                unique.setdefault(item["url"], dict(item))
        items = list(unique.values())[:20]
        if status and items:
            status("正在分析课程目录")
        for item in items[:max_reads]:
            if cancel and cancel.is_set():
                raise TrackerError("检索已取消", "cancelled", 409)
            try:
                page = self.reader.read(item["url"])
                reads += 1
            except TrackerError:
                item["verification_status"] = "search_result_only"
                continue
            item["verification_status"] = "content_verified" if page["text"] else "metadata_verified"
            item["metadata"] = {"page_title": page["title"] or "unknown",
                                "headings": page["headings"][:12],
                                "description": page["description"] or "unknown",
                                "language": "unknown", "level": "unknown", "duration": "unknown"}
            item["snippet"] = (page["description"] or item["snippet"])[:700]
            if page["url"] != item["url"]:
                item["metadata"]["final_url"] = page["url"]
        for item in items:
            item["score"] = self._score(item, topic)
        items.sort(key=lambda item: item["score"], reverse=True)
        return {"layer": layer, "topic": topic, "results": items[:20], "warnings": warnings[:5],
                "searches": calls, "reads": reads, "budget_exhausted": calls >= max_searches}

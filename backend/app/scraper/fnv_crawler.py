from __future__ import annotations

import asyncio
import heapq
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.domain import CaoPage, DiscoveredPdf
from app.utils.text import clean_whitespace, normalize_html_url, parse_term, slugify

FNV_HOSTS = {"www.fnv.nl", "fnv.nl"}
SKIP_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".css",
    ".js",
    ".zip",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
}


@dataclass(order=True, slots=True)
class QueueItem:
    priority: int
    depth: int
    url: str


class FnvCrawler:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        start_url: str,
        delay_seconds: float = 0.05,
    ) -> None:
        self.client = client
        self.start_url = normalize_html_url(start_url)
        self.delay_seconds = delay_seconds

    async def crawl(
        self,
        *,
        max_pages: int = 500,
        max_caos: int | None = None,
    ) -> list[CaoPage]:
        queue: list[QueueItem] = [QueueItem(0, 0, self.start_url)]
        queued = {self.start_url}
        visited: set[str] = set()
        results: dict[str, CaoPage] = {}

        while queue and len(visited) < max_pages:
            item = heapq.heappop(queue)
            url = item.url
            queued.discard(url)
            if url in visited:
                continue
            visited.add(url)

            html = await self._fetch_html(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            if self._is_cao_detail_page(url, soup):
                page = self._parse_cao_page(url, soup)
                if page.pdfs:
                    results[page.source_url] = page
                    if max_caos is not None and len(results) >= max_caos:
                        break

            for link in self._discover_html_links(url, soup):
                if link in visited or link in queued:
                    continue
                depth = item.depth + 1
                if depth > 7:
                    continue
                heapq.heappush(queue, QueueItem(self._priority(link), depth, link))
                queued.add(link)

            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)

        return sorted(results.values(), key=lambda page: page.name.lower())

    async def _fetch_html(self, url: str) -> str | None:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                return None
            return response.text
        except httpx.HTTPError:
            return None

    def _discover_html_links(self, base_url: str, soup: BeautifulSoup) -> list[str]:
        links: set[str] = set()
        for anchor in soup.select("a[href]"):
            href = clean_whitespace(anchor.get("href"))
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.hostname not in FNV_HOSTS:
                continue
            path = parsed.path.lower().rstrip("/")
            if not path.startswith("/cao-sector"):
                continue
            if any(path.endswith(suffix) for suffix in SKIP_SUFFIXES):
                continue
            if self._is_pdf_url(absolute):
                continue
            links.add(normalize_html_url(absolute))
        return sorted(links)

    def _is_cao_detail_page(self, url: str, soup: BeautifulSoup) -> bool:
        h1 = clean_whitespace(soup.select_one("h1").get_text(" ", strip=True)) if soup.select_one("h1") else ""
        page_text = clean_whitespace(soup.get_text(" ", strip=True)).lower()
        path_name = PurePosixPath(urlparse(url).path).name.lower()
        has_download = any(
            "download je cao" in clean_whitespace(anchor.get_text(" ", strip=True)).lower()
            for anchor in soup.select("a[href]")
        )
        return (
            (h1.lower().startswith("cao ") or path_name.startswith("cao-"))
            and has_download
            and "looptijd" in page_text
        )

    def _parse_cao_page(self, url: str, soup: BeautifulSoup) -> CaoPage:
        h1_tag = soup.select_one("h1")
        h1 = clean_whitespace(h1_tag.get_text(" ", strip=True) if h1_tag else "")
        name = h1 if h1.lower().startswith("cao ") else f"Cao {h1}"
        name = clean_whitespace(name)

        text = clean_whitespace(soup.get_text(" ", strip=True))
        term_match = re.search(
            r"Looptijd\s*:\s*(.+?)(?=(?:Actueel|Hoe komt|Word lid|$))",
            text,
            re.IGNORECASE,
        )
        effective_from, effective_to = parse_term(term_match.group(1) if term_match else text)

        path_parts = [part for part in urlparse(url).path.split("/") if part]
        sector = path_parts[1].replace("-", " ").title() if len(path_parts) > 1 else None

        return CaoPage(
            name=name,
            slug=slugify(name.removeprefix("Cao ").removeprefix("cao ")),
            sector=sector,
            source_url=normalize_html_url(url),
            effective_from=effective_from,
            effective_to=effective_to,
            pdfs=self._discover_pdfs(url, soup),
        )

    def _discover_pdfs(self, base_url: str, soup: BeautifulSoup) -> list[DiscoveredPdf]:
        pdfs: dict[str, DiscoveredPdf] = {}
        for anchor in soup.select("a[href]"):
            href = clean_whitespace(anchor.get("href"))
            absolute = urljoin(base_url, href)
            if not self._is_pdf_url(absolute):
                continue
            title = clean_whitespace(anchor.get_text(" ", strip=True)) or self._filename_from_url(absolute)
            pdfs[absolute] = DiscoveredPdf(
                title=title,
                url=absolute,
                document_type=self._classify_document(title, absolute),
            )
        return list(pdfs.values())

    @staticmethod
    def _is_pdf_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.path.lower().endswith(".pdf"):
            return True
        query = parse_qs(parsed.query)
        return any(
            str(value).lower().endswith(".pdf")
            for values in query.values()
            for value in values
        ) or "ext=.pdf" in parsed.query.lower()

    @staticmethod
    def _classify_document(title: str, url: str) -> str:
        value = f"{title} {url}".lower()
        if "salar" in value or "loon" in value:
            return "salary_table"
        if "bijlage" in value:
            return "appendix"
        if "wijzig" in value or "addendum" in value:
            return "amendment"
        if "cao" in value or "download je cao" in value:
            return "cao"
        return "other"

    @staticmethod
    def _filename_from_url(url: str) -> str:
        filename = PurePosixPath(urlparse(url).path).name
        return unquote(filename) or "document.pdf"

    @staticmethod
    def _priority(url: str) -> int:
        path = urlparse(url).path.lower()
        name = PurePosixPath(path).name
        if name.startswith("cao-"):
            return 0
        if path == "/cao-sector":
            return 1
        return 5

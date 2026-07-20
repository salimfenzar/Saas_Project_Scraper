from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class PdfDiscoveryError(Exception):
    """Fout tijdens het ophalen of verwerken van een CAO-pagina."""


def is_pdf_url(url: str) -> bool:
    parsed_url = urlparse(url)

    return parsed_url.path.lower().endswith(".pdf")

def classify_document(title: str | None, url: str) -> str:
    text = f"{title or ''} {url}".lower()

    if "sociaal plan" in text:
        return "social_plan"

    if any(
        keyword in text
        for keyword in (
            "salaristabel",
            "salarisschaal",
            "loontabel",
            "loonschaal",
        )
    ):
        return "salary_table"

    if "cao" in text:
        return "cao"

    return "other"

def discover_pdf_links(page_url: str) -> list[dict[str, str | None]]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; CAOMonitorBot/0.1; "
            "+https://example.com)"
        )
    }

    try:
        response = httpx.get(
            page_url,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()

    except httpx.HTTPError as exc:
        raise PdfDiscoveryError(
            f"De pagina kon niet worden opgehaald: {exc}"
        ) from exc

    soup = BeautifulSoup(response.text, "html.parser")

    found_pdfs: dict[str, dict[str, str | None]] = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")

        if not isinstance(href, str):
            continue

        absolute_url = urljoin(str(response.url), href)

        if not is_pdf_url(absolute_url):
            continue

        title = anchor.get_text(" ", strip=True) or None

        found_pdfs[absolute_url] = {
            "title": title,
            "url": absolute_url,
            "document_type": classify_document(
                title=title,
                url=absolute_url,
            ),
        }

    return list(found_pdfs.values())
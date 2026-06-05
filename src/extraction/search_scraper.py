"""
SearchScraper extracts job cards from the LinkedIn Jobs search results list.

The left panel gives us the card metadata. The right panel contains the full
job description, which we now anchor on the visible "Sobre a vaga" field.
"""

import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import ElementHandle, Page

from models.job import Job


CARD_SELECTOR = "div[data-view-name='job-search-job-card']"
DISMISS_BTN_SELECTOR = "button[data-view-name='dismiss-job']"
PAGE_SIZE = 25

D_CARD_SELECTORS = (
    "div[data-view-name='job-search-job-card']",
    "li[data-view-name='job-search-job-card']",
    "li.jobs-search-results__list-item",
    "li.artdeco-list__item",
    "div.job-card-container",
    "div.job-card-container--clickable",
    "li.scaffold-layout__list-item",
    "a[href*='/jobs/view/']",
)

_WORKPLACE_MAP = {
    "híbrido": "Hybrid",
    "hybrid": "Hybrid",
    "remoto": "Remote",
    "remote": "Remote",
    "presencial": "On-site",
    "on-site": "On-site",
    "on site": "On-site",
    "in person": "On-site",
}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clean_description(text: str) -> Optional[str]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return None

    cleaned = re.sub(r"^sobre a vaga\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = _normalize_text(cleaned)

    return cleaned or None


def _extract_title(card: ElementHandle) -> Optional[str]:
    btn = card.query_selector(DISMISS_BTN_SELECTOR)
    if not btn:
        return None

    label = (btn.get_attribute("aria-label") or "").strip()
    if not label:
        return None

    if " de " in label:
        title = label.split(" de ", 1)[1].strip()
    else:
        parts = label.split(None, 1)
        title = parts[1].strip() if len(parts) > 1 else label

    return title or None


def _extract_paragraphs(card: ElementHandle, title: Optional[str]) -> list[str]:
    texts: list[str] = card.evaluate(
        """el => Array.from(el.querySelectorAll("p"))
               .map(p => p.textContent.trim())
               .filter(t => t.length > 0 && t.length < 200)"""
    )

    seen: set[str] = set()
    result: list[str] = []
    title_lower = (title or "").lower()

    for text in texts:
        if text in seen:
            continue
        seen.add(text)
        if title_lower and text.lower().startswith(title_lower):
            continue
        result.append(text)

    return result


def _classify_paragraphs(texts: list[str]) -> tuple[Optional[str], Optional[str]]:
    location_signals = {
        "remoto",
        "híbrido",
        "presencial",
        "remote",
        "hybrid",
        "on-site",
        "região",
        "region",
    }

    company: Optional[str] = None
    location: Optional[str] = None

    for text in texts:
        text_lower = text.lower()
        if len(text) < 3:
            continue

        is_location = (
            any(signal in text_lower for signal in location_signals)
            or bool(re.search(r"\([^)]+\)", text))
        )

        if is_location and location is None:
            location = text
        elif not is_location and company is None:
            company = text

        if company and location:
            break

    return company, location


def _extract_workplace_type(location: Optional[str]) -> Optional[str]:
    if not location:
        return None

    match = re.search(r"\(([^)]+)\)", location)
    if match:
        raw = match.group(1).strip().lower()
        return _WORKPLACE_MAP.get(raw, match.group(1).strip())
    return None


def _build_page_url(base_url: str, start: int) -> str:
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("currentJobId", None)
    params.pop("start", None)
    if start > 0:
        params["start"] = [str(start)]
    new_query = urlencode({key: values[0] for key, values in params.items()})
    return urlunparse(parsed._replace(query=new_query))


class SearchScraper:
    def __init__(self, page: Page) -> None:
        self._page = page

    def scrape(self) -> list[Job]:
        print("[SearchScraper] Waiting for job cards to appear...")
        base_url = self._wait_for_cards()

        timestamp = datetime.now(timezone.utc)
        all_jobs: list[Job] = []
        page_num = 1
        start = 0

        while True:
            print(f"\n[SearchScraper] Page {page_num} (start={start})...")

            if not self._wait_for_result_items(timeout_s=30):
                print("  No cards appeared - end of results.")
                break

            self._page.wait_for_timeout(1200)
            cards = self._collect_card_handles()
            print(f"  Cards on this page: {len(cards)}")

            if not cards:
                break

            page_jobs = self._extract_cards(
                cards,
                search_url=base_url,
                timestamp=timestamp,
                page_num=page_num,
            )
            all_jobs.extend(page_jobs)

            if len(cards) < PAGE_SIZE:
                break

            if len(page_jobs) == 0:
                print("  All cards skipped - end of real results.")
                break

            start += PAGE_SIZE
            page_num += 1
            print(f"  Looking for next-page button (start={start})...")

            if self._click_next_page():
                print("  Clicked next-page button (SPA navigation).")
            else:
                next_url = _build_page_url(base_url, start)
                print("  Next button not found, falling back to URL navigation.")
                print(f"  -> {next_url[:100]}")
                self._page.goto(next_url, wait_until="load", timeout=60000)

        print(f"\n[SearchScraper] Done. Total extracted: {len(all_jobs)}")
        return all_jobs

    def _wait_for_cards(self) -> str:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                live_url: str = self._page.evaluate("() => window.location.href")
                if "jobs/search" in live_url:
                    break
            except Exception:
                pass
            self._page.wait_for_timeout(500)
        else:
            raise RuntimeError(
                "Still on the LinkedIn Jobs homepage after 30 s.\n"
                "Run a search and wait for results before pressing ENTER."
            )

        # Do not hard-fail here if LinkedIn is still painting the list or the
        # visible cards are exposed through a slightly different DOM shape.
        self._wait_for_result_items(timeout_s=12)

        return self._page.evaluate("() => window.location.href")

    def _wait_for_result_items(self, timeout_s: float = 30.0) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            cards = self._collect_card_handles()
            if cards:
                return True
            self._page.wait_for_timeout(250)
        return False

    def _collect_card_handles(self) -> list[ElementHandle]:
        cards: list[ElementHandle] = []
        seen_keys: set[str] = set()

        for selector in D_CARD_SELECTORS:
            for handle in self._page.query_selector_all(selector):
                if not self._is_visible(handle):
                    continue
                key = self._card_key(handle)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                cards.append(handle)

        anchors = [
            handle
            for handle in self._page.query_selector_all(DISMISS_BTN_SELECTOR)
            if self._is_visible(handle)
        ]
        for anchor in anchors:
            card = self._recover_card_from_anchor(anchor)
            if not card:
                continue
            key = self._card_key(card)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            cards.append(card)

        return cards

    def _card_key(self, card: ElementHandle) -> str:
        try:
            return card.evaluate("el => el.outerHTML")
        except Exception:
            return str(id(card))

    def _is_visible(self, handle: ElementHandle) -> bool:
        try:
            return bool(
                handle.evaluate(
                    """
                    el => {
                        const style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }
                    """
                )
            )
        except Exception:
            return False

    def _recover_card_from_anchor(self, anchor: ElementHandle) -> Optional[ElementHandle]:
        try:
            candidate = anchor.evaluate_handle(
                """
                el => {
                    const isCardLike = (node) => {
                        if (!node || !node.querySelectorAll) return false;
                        const titleButtons = node.querySelectorAll('button[data-view-name="dismiss-job"]').length;
                        const paragraphs = node.querySelectorAll('p').length;
                        const links = node.querySelectorAll('a[href*="/jobs/view/"]').length;
                        return titleButtons >= 1 && (paragraphs >= 2 || links >= 1);
                    };

                    let current = el;
                    for (let depth = 0; current && depth < 8; depth += 1) {
                        if (isCardLike(current)) {
                            return current;
                        }
                        current = current.parentElement;
                    }
                    return el.parentElement || el;
                }
                """
            )
            return candidate.as_element()
        except Exception:
            return None

    def _extract_cards(
        self,
        cards: list[ElementHandle],
        search_url: str,
        timestamp: datetime,
        page_num: int,
    ) -> list[Job]:
        print(f"  Extracting {len(cards)} cards (clicking each to get job ID and description)...")
        jobs: list[Job] = []
        skipped = 0
        total = len(cards)

        for i, card in enumerate(cards):
            job = self._parse_card(card, search_url=search_url, timestamp=timestamp)
            if job:
                jobs.append(job)
                description_state = "yes" if job.description else "no"
                print(
                    f"  [{(page_num - 1) * PAGE_SIZE + i + 1:>4}] "
                    f"{job.title} - {job.company} ({job.location}) | description: {description_state}"
                )
            else:
                skipped += 1

        if skipped:
            print(f"  Skipped {skipped}/{total} card(s) with missing fields.")

        return jobs

    def _click_next_page(self) -> bool:
        clicked: bool = self._page.evaluate(
            """
            () => {
                const candidates = Array.from(
                    document.querySelectorAll('button, a, [role="button"]')
                );
                const next = candidates.find(el => {
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
                        return false;
                    }
                    const label = (el.getAttribute('aria-label') || '').toLowerCase();
                    const text = (el.textContent || '').trim();
                    return (
                        label.includes('próxima') ||
                        label.includes('next page') ||
                        text === 'Próxima' ||
                        text === 'Next'
                    );
                });
                if (next) {
                    next.click();
                    return true;
                }
                return false;
            }
            """
        )
        return bool(clicked)

    def _click_card_and_extract_details(self, card: ElementHandle) -> tuple[Optional[str], Optional[str]]:
        click_targets = [
            card,
            card.query_selector("a[href*='/jobs/view/']"),
            card.query_selector("button[aria-label*='vaga']"),
            card.query_selector("button[aria-label*='job']"),
            card.query_selector("[role='button']"),
        ]

        for target in click_targets:
            if not target:
                continue
            try:
                target.scroll_into_view_if_needed()
            except Exception:
                pass
            try:
                target.click(timeout=3000)
                break
            except Exception:
                continue
        else:
            try:
                card.evaluate(
                    """el => {
                        el.scrollIntoView({ block: 'center', inline: 'nearest' });
                        el.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                        }));
                    }"""
                )
            except Exception:
                return None, None

        job_id = self._wait_for_job_id()
        description = self._wait_for_description()
        return job_id, description

    def _wait_for_job_id(self, timeout_s: float = 5.0) -> Optional[str]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                url = self._page.evaluate("() => window.location.href")
                match = re.search(r"currentJobId=(\d+)", url)
                if match:
                    return match.group(1)
            except Exception:
                pass
            self._page.wait_for_timeout(150)
        return None

    def _wait_for_description(self, timeout_s: float = 6.0) -> Optional[str]:
        deadline = time.time() + timeout_s
        last_description: Optional[str] = None

        while time.time() < deadline:
            expanded_any = False
            for _ in range(6):
                expanded = self._expand_description_in_detail_pane()
                if not expanded:
                    break
                expanded_any = True
                self._page.wait_for_timeout(250)
            if expanded_any:
                self._page.wait_for_timeout(300)

            description = self._extract_description_from_detail_pane()
            if description:
                cleaned = _clean_description(description)
                if cleaned:
                    last_description = cleaned
                    if len(cleaned) >= 40:
                        return cleaned
            self._page.wait_for_timeout(200)

        return last_description

    def _expand_description_in_detail_pane(self) -> bool:
        return bool(
            self._page.evaluate(
                """
                () => {
                    const normalize = (value) => (value || '')
                        .replace(/\\r\\n/g, '\\n')
                        .replace(/\\r/g, '\\n')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toLowerCase();

                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    const isRightPane = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.left >= 280 && rect.width >= 320;
                    };

                    const isMoreButton = (el) => {
                        if (!el || !isVisible(el)) return false;
                        const tag = (el.tagName || '').toLowerCase();
                        if (tag !== 'button' && el.getAttribute('role') !== 'button') {
                            return false;
                        }
                        const label = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                        if (!label) return false;
                        if (/demais\b/.test(label)) return false;
                        return (
                            label === 'mais' ||
                            label === 'more' ||
                            label.endsWith(' mais') ||
                            label.endsWith(' more') ||
                            label.includes('… mais') ||
                            label.includes('... mais') ||
                            label.includes('ver mais') ||
                            label.includes('veja mais') ||
                            label.includes('see more') ||
                            label.includes('show more') ||
                            label.includes('expandir') ||
                            label.includes('expand') ||
                            label.includes('show all')
                        );
                    };

                    const buttons = Array.from(
                        document.querySelectorAll('button, [role="button"]')
                    )
                        .filter(isMoreButton)
                        .filter(isRightPane)
                        .sort((a, b) => {
                            const ar = a.getBoundingClientRect();
                            const br = b.getBoundingClientRect();
                            if (ar.top !== br.top) return ar.top - br.top;
                            if (ar.left !== br.left) return ar.left - br.left;
                            return ar.width - br.width;
                        });

                    for (const button of buttons) {
                        try {
                            button.click();
                            return true;
                        } catch (err) {
                            try {
                                button.dispatchEvent(new MouseEvent('click', {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window,
                                }));
                                return true;
                            } catch (err2) {
                                continue;
                            }
                        }
                    }

                    return false;
                }
                """
            )
        )

    def _extract_description_from_detail_pane(self) -> Optional[str]:
        return self._page.evaluate(
            """
            () => {
                const normalize = (value) => (value || '')
                    .replace(/\\r\\n/g, '\\n')
                    .replace(/\\r/g, '\\n')
                    .replace(/\\s+/g, ' ')
                    .trim();

                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden') {
                        return false;
                    }
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };

                const all = Array.from(document.querySelectorAll('section, article, div, p, h1, h2, h3, h4, h5, h6'))
                    .filter(isVisible);

                const candidates = all
                    .map(el => {
                        const text = normalize(el.innerText || el.textContent || '');
                        if (!text) return null;
                        const lower = text.toLowerCase();
                        if (!lower.startsWith('sobre a vaga')) return null;
                        const rect = el.getBoundingClientRect();
                        return {
                            text,
                            len: text.length,
                            left: rect.left,
                            width: rect.width,
                            top: rect.top
                        };
                    })
                    .filter(Boolean)
                    .filter(c => c.len >= 20)
                    .filter(c => c.left >= 300 || c.width >= 350);

                if (!candidates.length) {
                    return null;
                }

                candidates.sort((a, b) => {
                    if (a.left !== b.left) return b.left - a.left;
                    if (a.width !== b.width) return b.width - a.width;
                    return a.len - b.len;
                });

                return candidates[0].text;
            }
            """
        )

    def _parse_card(self, card: ElementHandle, search_url: str, timestamp: datetime) -> Optional[Job]:
        title = _extract_title(card)
        if not title:
            return None

        paragraphs = _extract_paragraphs(card, title=title)
        company, location = _classify_paragraphs(paragraphs)
        if not company:
            return None

        workplace_type = _extract_workplace_type(location)
        job_id, description = self._click_card_and_extract_details(card)
        if not job_id:
            return None

        return Job(
            scrape_timestamp=timestamp,
            source_platform="linkedin",
            source_search_url=search_url,
            linkedin_job_id=job_id,
            title=title,
            company=company,
            location=location,
            workplace_type=workplace_type,
            job_url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            description=description,
        )

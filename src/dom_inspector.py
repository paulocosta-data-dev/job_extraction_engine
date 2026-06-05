"""
DOM inspector — discovers LinkedIn job IDs and card structure on the live page.

Run from: job_extraction_engine/
Command:  python src/dom_inspector.py
"""

import re
import time

from extraction.browser import BrowserManager, ChromeConflictError

WAIT_TIMEOUT_S = 20


def wait_for_page_settle(page) -> str:
    # Wait for any in-flight navigation to complete before touching the page.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass

    deadline = time.time() + WAIT_TIMEOUT_S
    prev_url = ""
    for _ in range(25):
        if time.time() > deadline:
            break
        try:
            live_url = page.evaluate("() => window.location.href")
        except Exception:
            # Context briefly destroyed during navigation — retry.
            time.sleep(1)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            continue
        if "jobs/search" in live_url and live_url == prev_url:
            print()
            return live_url
        prev_url = live_url
        print(f"\r  URL stabilising: {live_url[:80]}...", end="", flush=True)
        time.sleep(0.8)
    print()
    try:
        return page.evaluate("() => window.location.href")
    except Exception:
        return page.url


def inspect(page) -> None:
    current_url = page.evaluate("() => window.location.href")
    print(f"\n  Live URL: {current_url[:120]}")

    js = """
    () => {
        const results = {};

        // ---------------------------------------------------------------
        // Strategy 1: regex — find all 10-digit numbers in the full HTML.
        // LinkedIn job IDs are always 10 digits.
        // ---------------------------------------------------------------
        const html = document.body.innerHTML;
        const allMatches = html.match(/\\b\\d{10}\\b/g) || [];
        const uniqueIds = [...new Set(allMatches)];
        results.job_ids_from_html = uniqueIds.slice(0, 30);
        results.total_10digit_numbers = uniqueIds.length;

        // ---------------------------------------------------------------
        // Strategy 2: for each candidate ID, find the DOM element that
        // references it and walk up to understand the card structure.
        // We search text content nodes for each ID.
        // ---------------------------------------------------------------
        const idContexts = [];
        for (const id of uniqueIds.slice(0, 5)) {
            // Find the smallest element whose outerHTML contains this ID
            const all = Array.from(document.querySelectorAll("*"));
            const container = all.find(el =>
                el.children.length === 0 &&
                el.outerHTML.includes(id)
            ) || all.find(el => el.outerHTML.includes(id));

            if (!container) continue;

            // Walk up to the first element with > 2 children (the card)
            let card = container;
            let depth = 0;
            while (card && card.children.length < 3 && depth < 15) {
                card = card.parentElement;
                depth++;
            }

            idContexts.push({
                id: id,
                found_in_tag: container.tagName,
                found_in_attr_or_text: container.outerHTML.slice(0, 150),
                card_tag: card ? card.tagName : null,
                card_classes: card ? card.className : null,
                card_attrs: card ? Object.fromEntries(
                    Array.from(card.attributes).map(a => [a.name, a.value])
                ) : {},
                card_html: card ? card.outerHTML.slice(0, 600) : null,
            });
        }
        results.id_contexts = idContexts;

        // ---------------------------------------------------------------
        // Strategy 3: data-view-name attributes — LinkedIn uses these for
        // component analytics and they tend to be stable.
        // ---------------------------------------------------------------
        const viewNames = Array.from(
            document.querySelectorAll("[data-view-name]")
        ).map(el => ({
            tag: el.tagName,
            data_view_name: el.getAttribute("data-view-name"),
            classes: el.className,
            attrs: Object.fromEntries(
                Array.from(el.attributes).map(a => [a.name, a.value])
            ),
            html: el.outerHTML.slice(0, 300),
        }));
        results.view_name_elements = viewNames;

        // ---------------------------------------------------------------
        // Strategy 4: find text nodes matching job-title-like text
        // (known titles from the screenshot for cross-referencing).
        // ---------------------------------------------------------------
        const titlesToFind = [
            "Analytics Engineer", "Analytics Expert",
            "BI Lead", "Senior Analytics Consultant",
            "InnoTech", "Körber", "Siemens Energy"
        ];
        const titleMatches = [];
        for (const title of titlesToFind) {
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT
            );
            let node;
            while ((node = walker.nextNode())) {
                if (node.textContent.trim() === title) {
                    const el = node.parentElement;
                    // Walk up to a card-like ancestor
                    let card = el;
                    let d = 0;
                    while (card && card.children.length < 3 && d < 12) {
                        card = card.parentElement;
                        d++;
                    }
                    titleMatches.push({
                        text: title,
                        el_tag: el.tagName,
                        el_classes: el.className,
                        card_tag: card ? card.tagName : null,
                        card_classes: card ? card.className : null,
                        card_attrs: card ? Object.fromEntries(
                            Array.from(card.attributes).map(a => [a.name, a.value])
                        ) : {},
                        card_html: card ? card.outerHTML.slice(0, 800) : null,
                    });
                    break;
                }
            }
        }
        results.title_matches = titleMatches;

        return results;
    }
    """

    data = page.evaluate(js)

    print("\n" + "=" * 60)
    print("DOM INSPECTION RESULTS")
    print("=" * 60)

    # --- Strategy 1: raw ID extraction ---
    print(f"\n[1] 10-digit numbers found in raw HTML: {data['total_10digit_numbers']}")
    print(f"    Candidate job IDs: {data['job_ids_from_html']}")

    # --- Strategy 2: ID contexts ---
    print(f"\n[2] DOM context for first 5 IDs:")
    for ctx in data["id_contexts"]:
        print(f"\n  ID: {ctx['id']}")
        print(f"    Found in:    <{ctx['found_in_tag']}>")
        print(f"    Found HTML:  {ctx['found_in_attr_or_text']!r}")
        print(f"    Card tag:    {ctx['card_tag']}")
        print(f"    Card class:  {ctx['card_classes']!r}")
        print(f"    Card attrs:  {ctx['card_attrs']}")
        print(f"    Card HTML:   {ctx['card_html']!r}")

    # --- Strategy 3: data-view-name ---
    print(f"\n[3] Elements with data-view-name: {len(data['view_name_elements'])}")
    for el in data["view_name_elements"]:
        print(f"\n  data-view-name={el['data_view_name']!r}")
        print(f"    tag:   {el['tag']}")
        print(f"    attrs: {el['attrs']}")
        print(f"    html:  {el['html']!r}")

    # --- Strategy 4: known title matches ---
    print(f"\n[4] Known job title text nodes found: {len(data['title_matches'])}")
    for match in data["title_matches"]:
        print(f"\n  Text: {match['text']!r}")
        print(f"    el:        <{match['el_tag']} class={match['el_classes']!r}>")
        print(f"    card:      <{match['card_tag']} class={match['card_classes']!r}>")
        print(f"    card attrs:{match['card_attrs']}")
        print(f"    card HTML: {match['card_html']!r}")

    print("\n" + "=" * 60)


def main() -> None:
    browser_manager = BrowserManager()

    try:
        browser_manager.launch()
        page = browser_manager.get_active_page()

        print("Navigating to LinkedIn Jobs...")
        page.goto(
            "https://www.linkedin.com/jobs/",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        print("\n" + "=" * 60)
        print("ACTION REQUIRED:")
        print("  1. Search for a role + location")
        print("  2. Wait for the left-panel results list to fully load")
        print("  3. Come back here and press ENTER")
        print("=" * 60)
        input("\nPress ENTER when results are loaded...\n")

        print("Waiting for URL to stabilise...")
        live_url = wait_for_page_settle(page)
        print(f"Final URL: {live_url[:100]}")

        inspect(page)

        input("\nPress ENTER to close the browser...")

    except ChromeConflictError as e:
        print(f"\nERROR: {e}")

    finally:
        browser_manager.close()


if __name__ == "__main__":
    main()

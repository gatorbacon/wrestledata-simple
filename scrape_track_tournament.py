#!/usr/bin/env python3
"""
Scrape tournament results from TrackWrestling.

Reuses the session setup from wrestle_scraper_raw_mt_locked.py to log in,
then navigates to a tournament URL, clicks Results > Text Results,
and filters by weight class. Includes debug output for common scraping issues.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.common.exceptions import TimeoutException

# Import scraper for session setup
from wrestle_scraper_raw_mt_locked import WrestlingScraper, BASE_URL

# Tournament URL template - direct to TournamentHub frame (no MainFrame wrapper)
# TIM = current timestamp to avoid cache
TOURNAMENT_URL_TEMPLATE = (
    "https://www.trackwrestling.com/predefinedtournaments/TournamentHub.jsp"
    "?TIM={tim}&twSessionId={session_id}"
)


def _debug_all_links(driver, context: str = ""):
    """Print all links on the page for debugging."""
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        print(f"\n[DEBUG {context}] Found {len(links)} links:")
        for i, link in enumerate(links[:50]):  # Limit to first 50
            try:
                text = (link.text or "").strip()
                href = link.get_attribute("href") or ""
                if text or href:
                    print(f"  {i+1}. text='{text[:60]}' href='{href[:80]}...'")
            except Exception as e:
                print(f"  {i+1}. (error reading: {e})")
        if len(links) > 50:
            print(f"  ... and {len(links) - 50} more")
    except Exception as e:
        print(f"[DEBUG {context}] Error listing links: {e}")


def _debug_all_selects(driver, context: str = ""):
    """Print all select/dropdown elements for debugging."""
    try:
        selects = driver.find_elements(By.TAG_NAME, "select")
        print(f"\n[DEBUG {context}] Found {len(selects)} select elements:")
        for i, sel in enumerate(selects):
            try:
                name = sel.get_attribute("name") or sel.get_attribute("id") or "(no name/id)"
                label = sel.get_attribute("aria-label") or ""
                options = [o.text.strip() for o in sel.find_elements(By.TAG_NAME, "option") if o.text.strip()]
                print(f"  {i+1}. name/id='{name}' aria-label='{label}' options={options[:10]}{'...' if len(options) > 10 else ''}")
            except Exception as e:
                print(f"  {i+1}. (error: {e})")
    except Exception as e:
        print(f"[DEBUG {context}] Error listing selects: {e}")


def _debug_all_buttons(driver, context: str = ""):
    """Print all buttons and inputs for debugging."""
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, "button, input[type='button'], input[type='submit']")
        print(f"\n[DEBUG {context}] Found {len(buttons)} buttons:")
        for i, btn in enumerate(buttons[:30]):
            try:
                text = (btn.text or btn.get_attribute("value") or "").strip()
                if text:
                    print(f"  {i+1}. '{text}'")
            except Exception:
                pass
    except Exception as e:
        print(f"[DEBUG {context}] Error listing buttons: {e}")


def _debug_frames(driver, context: str = ""):
    """Print all frames for debugging."""
    try:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"\n[DEBUG {context}] Found {len(frames)} iframes:")
        for i, f in enumerate(frames):
            name = f.get_attribute("name") or f.get_attribute("id") or "(unnamed)"
            print(f"  {i+1}. name/id='{name}'")
    except Exception as e:
        print(f"[DEBUG {context}] Error listing frames: {e}")


def _find_and_click_link(driver, wait, text: str, partial: bool = True) -> bool:
    """Find a link by text and click it. Returns True on success."""
    try:
        if partial:
            link = wait.until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, text))
            )
        else:
            link = wait.until(
                EC.element_to_be_clickable((By.LINK_TEXT, text))
            )
        print(f"[OK] Clicking link: '{text}'")
        link.click()
        time.sleep(1.5)
        return True
    except TimeoutException:
        print(f"[FAIL] Link not found: looking for '{text}'")
        _debug_all_links(driver, f"link '{text}' not found")
        return False
    except Exception as e:
        print(f"[FAIL] Error clicking link '{text}': {e}")
        _debug_all_links(driver, f"link '{text}' error")
        return False


def _find_select_by_label(driver, label_text: str) -> Optional[Select]:
    """Find a select by its associated label. Returns Select or None."""
    # Try to find label containing the text, then get the for= attribute
    try:
        labels = driver.find_elements(By.TAG_NAME, "label")
        for label in labels:
            if label_text.lower() in (label.text or "").lower():
                for_id = label.get_attribute("for")
                if for_id:
                    sel = driver.find_element(By.ID, for_id)
                    return Select(sel)
        # Try finding select with name containing the label
        selects = driver.find_elements(By.TAG_NAME, "select")
        for sel in selects:
            name = (sel.get_attribute("name") or "").lower()
            id_attr = (sel.get_attribute("id") or "").lower()
            if label_text.lower().replace(" ", "") in name.replace("_", "") or label_text.lower().replace(" ", "") in id_attr.replace("_", ""):
                return Select(sel)
        return None
    except Exception as e:
        print(f"[DEBUG] Error finding select by label '{label_text}': {e}")
        return None


def _find_select_and_select_option(driver, label_or_name: str, option_value: str) -> bool:
    """Find a select by label/name and select an option. Returns True on success."""
    # First try by label
    select = _find_select_by_label(driver, label_or_name)
    if not select:
        # Try by name
        try:
            sel_el = driver.find_element(By.CSS_SELECTOR, f"select[name*='{label_or_name}'], select[id*='{label_or_name}']")
            select = Select(sel_el)
        except Exception:
            pass
    if not select:
        print(f"[FAIL] Select not found: '{label_or_name}'")
        _debug_all_selects(driver, f"select '{label_or_name}' not found")
        return False

    options = [o.text.strip() for o in select.options]
    print(f"[DEBUG] Select '{label_or_name}' options: {options}")

    # Try by visible text first
    try:
        select.select_by_visible_text(option_value)
        print(f"[OK] Selected '{option_value}' in '{label_or_name}'")
        return True
    except Exception:
        pass

    # Try partial match
    for opt in select.options:
        if option_value in (opt.text or "").strip():
            opt.click()
            print(f"[OK] Selected '{opt.text.strip()}' in '{label_or_name}'")
            return True

    print(f"[FAIL] Option '{option_value}' not found in select '{label_or_name}'")
    print(f"  Available options: {options}")
    return False


def _find_and_click_button(driver, wait, text: str) -> bool:
    """Find a button by value/text and click it. Returns True on success."""
    try:
        btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, f"//input[@value='{text}'] | //button[contains(text(),'{text}')]"))
        )
        print(f"[OK] Clicking button: '{text}'")
        btn.click()
        time.sleep(1)
        return True
    except TimeoutException:
        print(f"[FAIL] Button not found: '{text}'")
        _debug_all_buttons(driver, f"button '{text}' not found")
        return False
    except Exception as e:
        print(f"[FAIL] Error clicking button '{text}': {e}")
        _debug_all_buttons(driver, f"button '{text}' error")
        return False


def _navigate_to_tournament_via_ui(driver, wait, tournament_id: str) -> None:
    """
    Navigate to tournament by clicking through the site UI (Events -> tournament).
    Preserves session context that direct URL loses.
    """
    driver.switch_to.default_content()
    print(f"\n2. Navigating to tournament via UI (ID={tournament_id})...")

    # Click EVENTS CLASSIC to go to events list (Login.jsp with our session)
    print("[DEBUG] Clicking 'EVENTS CLASSIC' to open events list...")
    try:
        events_link = wait.until(
            EC.element_to_be_clickable((By.LINK_TEXT, "EVENTS CLASSIC"))
        )
        events_link.click()
        time.sleep(3)
    except TimeoutException:
        print("[FAIL] 'EVENTS CLASSIC' link not found")
        _debug_all_links(driver, "EVENTS CLASSIC not found")
        raise
    except Exception as e:
        print(f"[FAIL] Error clicking EVENTS CLASSIC: {e}")
        _debug_all_links(driver, "EVENTS CLASSIC error")
        raise

    print(f"[DEBUG] Current URL after Events: {driver.current_url}")

    # Find and click the tournament by ID (eventSelected(tournament_id, ...))
    print(f"[DEBUG] Looking for tournament with ID {tournament_id}...")
    try:
        # eventSelected(ID, 'Name', ...) - find element with this ID in href or onclick
        id_pattern = f"eventSelected({tournament_id},"
        event_links = driver.find_elements(
            By.XPATH,
            f"//a[contains(@href, '{id_pattern}') or contains(@onclick, '{id_pattern}')]"
        )
        if not event_links:
            event_links = driver.find_elements(
                By.XPATH,
                f"//a[contains(@href, '{tournament_id}') or contains(@onclick, '{tournament_id}')]"
            )
        if not event_links:
            print(f"[FAIL] No event link found for tournament ID {tournament_id}")
            print("[DEBUG] Listing first 20 links with href/onclick for manual inspection:")
            links = driver.find_elements(By.TAG_NAME, "a")
            for i, link in enumerate(links[:20]):
                href = link.get_attribute("href") or ""
                onclick = link.get_attribute("onclick") or ""
                text = (link.text or "").strip()[:40]
                if "eventSelected" in href or "eventSelected" in onclick:
                    print(f"  {i+1}. text='{text}' href='{href[:70]}...' onclick='{onclick[:70]}...'")
            raise ValueError(f"Tournament ID {tournament_id} not found in event list")

        # Click the first matching link
        event_links[0].click()
        print(f"[OK] Clicked tournament {tournament_id}")
        time.sleep(3)

        # Check if a new window/popup opened
        handles = driver.window_handles
        if len(handles) > 1:
            driver.switch_to.window(handles[-1])
            print("[DEBUG] Switched to new window/tab")
            time.sleep(2)

        print(f"[DEBUG] Current URL after tournament click: {driver.current_url}")
        print(f"[DEBUG] Page title: {driver.title}")

    except Exception as e:
        print(f"[FAIL] Error selecting tournament: {e}")
        raise


def get_session_id(scraper) -> Optional[str]:
    """Extract twSessionId from current driver URL."""
    try:
        driver = scraper.driver
        # Events Classic (Login.jsp) is main document; Seasons uses PageFrame
        current_url = driver.current_url
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query)
        session_id = params.get("twSessionId", [""])[0]
        if not session_id:
            try:
                driver.switch_to.frame("PageFrame")
                current_url = driver.current_url
                driver.switch_to.default_content()
                parsed = urlparse(current_url)
                params = parse_qs(parsed.query)
                session_id = params.get("twSessionId", [""])[0]
            except Exception:
                pass
        return session_id if session_id else None
    except Exception as e:
        print(f"[FAIL] Could not extract session ID: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Scrape tournament results from TrackWrestling")
    parser.add_argument(
        "--tournament-url",
        help="Override tournament URL (must contain {session_id} placeholder). Default uses TournamentHub.",
    )
    parser.add_argument(
        "--weight",
        default="100",
        help="Weight class to select (default: 100)",
    )
    parser.add_argument(
        "--tournament-id",
        help="Tournament/event ID - 9-digit number from eventSelected (e.g. 929410132). Required for --navigate-via-ui.",
    )
    parser.add_argument(
        "--navigate-via-ui",
        action="store_true",
        help="Navigate to tournament via site menu (Events -> click tournament) instead of direct URL. Use when direct URL redirects to Login.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("TrackWrestling Tournament Scraper")
    print("=" * 60)

    # Use WrestlingScraper for session setup (HS KY boys 2026)
    scraper = WrestlingScraper(
        season_year=2026,
        headless=False,
        league="hs",
        state="ky",
        gender="boys",
    )

    print("\n1. Setting up browser: Browse -> Events Classic...")
    scraper.setup_driver()
    if not scraper.navigate_to_events_classic():
        print("[FAIL] Could not navigate to Events Classic. Aborting.")
        scraper.driver.quit()
        sys.exit(1)

    session_id = get_session_id(scraper)
    if not session_id:
        print("[FAIL] Could not get session ID. Aborting.")
        scraper.driver.quit()
        sys.exit(1)
    print(f"[OK] Session ID: {session_id}")

    driver = scraper.driver
    wait = scraper.wait

    if args.navigate_via_ui:
        # Navigate via site menu - avoids redirect when direct URL fails
        if not args.tournament_id:
            print("[FAIL] --tournament-id is required when using --navigate-via-ui")
            scraper.driver.quit()
            sys.exit(1)
        _navigate_to_tournament_via_ui(driver, wait, args.tournament_id)
    else:
        # Direct URL navigation
        tim = int(time.time() * 1000)
        if args.tournament_url:
            tournament_url = args.tournament_url.format(session_id=session_id)
        else:
            tournament_url = TOURNAMENT_URL_TEMPLATE.format(tim=tim, session_id=session_id)
            if args.tournament_id:
                sep = "&" if "?" in tournament_url else "?"
                tournament_url = f"{tournament_url}{sep}tournamentId={args.tournament_id}"

        print(f"\n2. Navigating to tournament (direct URL)...")
        print(f"[DEBUG] Full URL: {tournament_url}")
        driver.get(tournament_url)
        time.sleep(3)

        actual_url = driver.current_url
        print(f"\n[DEBUG] Actual URL: {actual_url}")
        print(f"[DEBUG] Page title: {driver.title}")

        if "Login.jsp" in actual_url:
            print("\n" + "=" * 60)
            print("[FAIL] REDIRECTED TO LOGIN PAGE")
            print("=" * 60)
            print("Direct URL redirects to Login. Try: --navigate-via-ui --tournament-id <ID>")
            print("Tournament IDs are 9-digit numbers from eventSelected (e.g. 929410132)")
            print("=" * 60)
            try:
                input("\nPress Enter to close browser...")
            except KeyboardInterrupt:
                pass
            scraper.driver.quit()
            sys.exit(1)

    # Debug: show frames
    _debug_frames(driver, "after tournament load")
    driver.switch_to.default_content()

    # 3. Click Results
    print("\n3. Looking for 'Results' link...")
    _find_and_click_link(driver, wait, "Results")
    time.sleep(2)

    # 4. Click Text Results
    print("\n4. Looking for 'Text Results' link...")
    if not _find_and_click_link(driver, wait, "Text Results"):
        _find_and_click_link(driver, wait, "Text")
    time.sleep(2)

    # 5. Display page contents to console
    print("\n5. Page contents:")
    print("-" * 60)
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        text = body.text
        print(text[:3000] if len(text) > 3000 else text)
        if len(text) > 3000:
            print(f"\n... (truncated, total {len(text)} chars)")
    except Exception as e:
        print(f"[FAIL] Could not get body text: {e}")
    print("-" * 60)

    # 6. Display By -> Weight Class
    print("\n6. Finding 'Display By' dropdown and selecting 'Weight Class'...")
    if not _find_select_and_select_option(driver, "Display By", "Weight Class"):
        _find_select_and_select_option(driver, "DisplayBy", "Weight Class")
    time.sleep(1)

    # 7. Weight Class -> selected weight
    weight = args.weight
    print(f"\n7. Finding 'Weight Class' dropdown and selecting '{weight}'...")
    if not _find_select_and_select_option(driver, "Weight Class", weight):
        _find_select_and_select_option(driver, "WeightClass", weight)
    time.sleep(1)

    # 8. Click Go
    print("\n8. Looking for 'Go' button...")
    if not _find_and_click_button(driver, wait, "Go"):
        # Try lowercase
        _find_and_click_button(driver, wait, "go")
    time.sleep(2)

    # 9. Display final page contents
    print("\n9. Final page contents (after Go):")
    print("-" * 60)
    try:
        driver.switch_to.default_content()
        body = driver.find_element(By.TAG_NAME, "body")
        text = body.text
        print(text[:5000] if len(text) > 5000 else text)
        if len(text) > 5000:
            print(f"\n... (truncated, total {len(text)} chars)")
    except Exception as e:
        print(f"[FAIL] Could not get final body text: {e}")
    print("-" * 60)

    print("\nDone. Browser will stay open for inspection (close manually or Ctrl+C).")
    try:
        input("Press Enter to close browser...")
    except KeyboardInterrupt:
        pass
    scraper.driver.quit()


if __name__ == "__main__":
    main()

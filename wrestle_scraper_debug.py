#!/usr/bin/env python3
"""
Debug harness for wrestle_scraper_raw_mt_locked.py -- scrapes ONE team (not
the whole season) and, on every error the scraper's own _log_error() call
already reports, additionally dumps a full diagnostic snapshot: the real
Python traceback (the normal error path only keeps str(e), which strips the
useful part of a Selenium WebDriverException), a screenshot, the page
source, and the current URL/title -- all to mt/debug_<season>/.

Built to chase down why `-season 2012` fails within ~1-2 minutes (a handful
of teams in) instead of running clean for tens of minutes like recent
seasons do. Runs single-instance (no parallel workers) so failures here
can't be explained by the Chrome-resource-contention issue already
diagnosed separately -- if it still fails fast solo, that points at
something about the 2012 season's actual pages.

Usage:
  .venv/bin/python wrestle_scraper_debug.py -season 2012 -team "Air Force"
  .venv/bin/python wrestle_scraper_debug.py -season 2012          # first team in the list
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import wrestle_scraper_raw_mt_locked as mod

PID = os.getpid()


class DebugScraper(mod.WrestlingScraper):
    def __init__(self, *args, debug_dir: Path, worker_id: str, reboot_after: int = None,
                 exit_after: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug_dir = debug_dir
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self._failure_count = 0
        self.worker_id = worker_id

        # Two competing "bigger hammer" experiments, mutually exclusive:
        #  - reboot_after: quit+relaunch the Selenium driver in-process (already tested; didn't fix it)
        #  - exit_after: exit the whole PYTHON PROCESS (code 2) so an external
        #    wrapper loop launches a brand-new process immediately, no cooldown.
        self.reboot_after = reboot_after
        self.exit_after = exit_after
        self._consecutive_team_failures = 0
        self._reboot_count = 0
        self._pending_verification = None  # set right after a reboot/restart

        # worker_id (stable across process restarts), not PID, so the log
        # stays one continuous timeline across a lineage of relaunches.
        self.event_log_path = self.debug_dir / f"{worker_id}_event_log.jsonl"
        self.restart_marker_path = self.debug_dir / f"{worker_id}_restart_pending.json"

        if self.exit_after is not None and self.restart_marker_path.exists():
            try:
                marker = json.loads(self.restart_marker_path.read_text())
                self._pending_verification = {"kind": "restart", "num": marker["restart_num"]}
                self.restart_marker_path.unlink()
                print(f"[worker {worker_id}] [pid {PID}] Fresh process after restart #{marker['restart_num']} -- "
                      f"will log outcome of the first team attempted.")
            except Exception as e:
                print(f"[worker {worker_id}] [pid {PID}] Could not read restart marker: {e}")

    def _log_event(self, event):
        event["timestamp"] = datetime.now().isoformat()
        event["pid"] = PID
        with open(self.event_log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def scrape_team(self, team_url, team_info):
        result = super().scrape_team(team_url, team_info)

        # If a reboot/restart just happened, this is the first team attempted
        # on the fresh driver/process -- log whether it actually recovered.
        if self._pending_verification is not None:
            outcome = "SUCCESS" if result else "STILL FAILING"
            kind = self._pending_verification["kind"]
            num = self._pending_verification["num"]
            print(f"[worker {self.worker_id}] [{kind.upper()}-CHECK] First team after {kind} #{num} "
                  f"({team_info['name']}): {outcome}")
            self._log_event({
                "event": f"post_{kind}_verification",
                "num": num,
                "team": team_info["name"],
                "outcome": outcome,
            })
            self._pending_verification = None

        threshold = self.exit_after if self.exit_after is not None else self.reboot_after
        if threshold is None:
            return result

        if result is None:
            self._consecutive_team_failures += 1
            print(f"[worker {self.worker_id}] consecutive team failures: "
                  f"{self._consecutive_team_failures}/{threshold} (last: {team_info['name']})")
            if self._consecutive_team_failures >= threshold:
                if self.exit_after is not None:
                    self._restart_process(triggered_by=team_info["name"])  # exits the process, does not return
                else:
                    self._reboot_driver(triggered_by=team_info["name"])
        else:
            if self._consecutive_team_failures > 0:
                print(f"[worker {self.worker_id}] streak broken at {self._consecutive_team_failures} "
                      f"(succeeded on {team_info['name']}) -- resetting counter")
            self._consecutive_team_failures = 0

        return result

    def _restart_process(self, triggered_by):
        self._reboot_count += 1
        print(f"[worker {self.worker_id}] [pid {PID}] [RESTART] >>> {self._consecutive_team_failures} consecutive "
              f"team failures (triggered by '{triggered_by}') -- exiting process for a full restart "
              f"(restart #{self._reboot_count}), no cooldown <<<")
        self._log_event({
            "event": "process_restart_triggered",
            "num": self._reboot_count,
            "consecutive_failures": self._consecutive_team_failures,
            "triggered_by_team": triggered_by,
        })
        self.restart_marker_path.write_text(json.dumps({"restart_num": self._reboot_count}))
        try:
            self.driver.quit()
        except Exception:
            pass
        sys.exit(2)  # distinct code so the wrapper loop knows to relaunch immediately

    def _reboot_driver(self, triggered_by):
        self._reboot_count += 1
        print(f"[worker {self.worker_id}] [pid {PID}] [REBOOT] >>> {self._consecutive_team_failures} consecutive "
              f"team failures (triggered by '{triggered_by}') -- rebooting driver (reboot #{self._reboot_count}) <<<")
        self._log_event({
            "event": "reboot_triggered",
            "num": self._reboot_count,
            "consecutive_failures": self._consecutive_team_failures,
            "triggered_by_team": triggered_by,
        })
        try:
            self.driver.quit()
        except Exception as e:
            print(f"[worker {self.worker_id}] [REBOOT] error quitting old driver: {e}")
        self.driver = None
        self.wait = None

        # Mirror run()'s own startup retry pattern -- a fresh setup can
        # itself fail transiently, and we don't want a bad reboot to leave
        # self.driver in a broken state for the next scrape_team() call.
        nav_ok = False
        for attempt in range(1, 4):
            try:
                self.setup_driver()
                nav_ok = self.navigate_to_season()
            except Exception as e:
                print(f"[worker {self.worker_id}] [REBOOT] setup/navigate attempt {attempt}/3 raised: {e}")
                nav_ok = False
            if nav_ok:
                break
            print(f"[worker {self.worker_id}] [REBOOT] setup/navigate attempt {attempt}/3 failed, retrying...")
            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self.wait = None
            time.sleep(5)

        print(f"[worker {self.worker_id}] [REBOOT] navigate_to_season after reboot: "
              f"{'OK' if nav_ok else 'FAILED (after 3 attempts)'}")
        self._log_event({
            "event": "reboot_navigation_result",
            "num": self._reboot_count,
            "navigate_ok": nav_ok,
        })

        self._consecutive_team_failures = 0
        self._pending_verification = {"kind": "reboot", "num": self._reboot_count}

    def _log_error(self, error_type, details):
        # Preserve normal behavior (writes to the real scrape log) so this
        # run's progress still counts toward the season like any other.
        super()._log_error(error_type, details)

        self._failure_count += 1
        # worker_id + PID in the filename so concurrent instances (and
        # process restarts under the same worker_id) sharing debug_dir don't
        # clobber each other.
        tag = f"{self.worker_id}_pid{PID}_failure_{self._failure_count:03d}_{error_type}"
        tb = traceback.format_exc()

        info = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "details": details,
            "traceback": tb,
        }
        try:
            info["current_url"] = self.driver.current_url
            info["title"] = self.driver.title
        except Exception as e:
            info["driver_state_error"] = repr(e)

        try:
            (self.debug_dir / f"{tag}.json").write_text(json.dumps(info, indent=2))
        except Exception as e:
            print(f"[DEBUG] couldn't write info json: {e}")

        try:
            self.driver.save_screenshot(str(self.debug_dir / f"{tag}.png"))
        except Exception as e:
            print(f"[DEBUG] couldn't save screenshot: {e}")

        try:
            (self.debug_dir / f"{tag}.html").write_text(self.driver.page_source)
        except Exception as e:
            print(f"[DEBUG] couldn't save page source: {e}")

        print(f"[DEBUG] >>> captured failure snapshot: {self.debug_dir / tag}.*")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-season", type=int, required=True)
    p.add_argument("-league", default="ncaa")
    p.add_argument("-gender", default="men")
    p.add_argument("-team", default=None, help="substring to match a team name; default: first team in the list")
    p.add_argument("-headless", action="store_true", default=True)
    p.add_argument("-no-headless", dest="headless", action="store_false")
    p.add_argument("-full-run", action="store_true",
                    help="Loop over ALL teams via the real run() method (same cross-process "
                         "locking as production) instead of just one team -- for reproducing "
                         "failures that only show up a few teams / a couple minutes in, "
                         "especially when running several instances of this concurrently.")
    p.add_argument("-reboot-after", type=int, default=None,
                    help="After this many CONSECUTIVE team-level failures, quit and relaunch "
                         "the driver (fresh Chrome + chromedriver, re-navigate into the season), "
                         "then log whether the next team succeeds. Off by default.")
    p.add_argument("-exit-after", type=int, default=None,
                    help="After this many CONSECUTIVE team-level failures, exit the whole process "
                         "with code 2 (an external wrapper loop should relaunch immediately) instead "
                         "of rebooting the driver in-process. Mutually exclusive with -reboot-after.")
    p.add_argument("-worker-id", default=None,
                    help="Stable id for this worker's lineage of processes (matters for -exit-after, "
                         "where PID changes every restart but the event log should stay continuous). "
                         "Defaults to this process's PID.")
    args = p.parse_args()

    worker_id = args.worker_id or str(PID)
    debug_dir = Path("mt/debug") / f"{args.league}_{args.gender}_{args.season}"

    scraper = DebugScraper(
        season_year=args.season,
        headless=args.headless,
        league=args.league,
        gender=args.gender,
        debug_dir=debug_dir,
        worker_id=worker_id,
        reboot_after=args.reboot_after,
        exit_after=args.exit_after,
    )

    print(f"[pid {PID}] === Setting up driver (headless={args.headless}) ===")

    if args.full_run:
        # Reuses the real run() loop: setup_driver + navigate_to_season with
        # its own retry logic, then iterates every team with the same
        # acquire_lock/release_lock per-team_id locking production uses, so
        # running several of these concurrently behaves like the real
        # multi-worker pipeline -- just with rich diagnostics on every error.
        print(f"[pid {PID}] === Full run over all teams (production-equivalent looping/locking) ===")
        scraper.run()
        print(f"[pid {PID}] ✅ run() returned -- {scraper._failure_count} error snapshots captured in {debug_dir}/")
        return

    scraper.setup_driver()

    print(f"[pid {PID}] === Navigating to season ===")
    nav_ok = scraper.navigate_to_season()
    if not nav_ok:
        print(f"[pid {PID}] FAILED to navigate to season -- see debug snapshots.")
        scraper.driver.quit()
        sys.exit(1)

    print(f"[pid {PID}] === Getting team list ===")
    teams = scraper.get_teams()
    print(f"[pid {PID}] Found {len(teams)} teams.")

    if args.team:
        matches = [t for t in teams if args.team.lower() in t["name"].lower()]
        if not matches:
            print(f"[pid {PID}] No team matching '{args.team}'. First 15: {[t['name'] for t in teams[:15]]}")
            scraper.driver.quit()
            sys.exit(1)
        team_info = matches[0]
    else:
        team_info = teams[0]

    print(f"[pid {PID}] === Scraping ONE team: {team_info['name']} -> {team_info['url']} ===")
    result = scraper.scrape_team(team_info["url"], team_info)

    if result:
        print(f"[pid {PID}] ✅ SUCCESS -- {len(result.get('roster', []))} wrestlers scraped, {scraper._failure_count} recoverable errors along the way.")
        scraper.save_team_data(result)
    else:
        print(f"[pid {PID}] ❌ FAILED -- team_data is None. {scraper._failure_count} errors captured in {debug_dir}/")

    scraper.driver.quit()


if __name__ == "__main__":
    main()

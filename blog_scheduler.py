"""
blog_scheduler.py — Automated 2x/Week Background Scheduler for PrestigePDF Blog System

Runs automated publishing twice a week (Tuesdays & Fridays at 09:00 AM)
or immediately on command (--now).
"""

import argparse
import datetime
import sys
import time
from blog_generator import generate_and_publish_post


def run_scheduler():
    """Background loop that publishes 2 blog posts per week (Tuesdays & Fridays at 09:00 AM)."""
    print("\n============================================================")
    print("  PrestigePDF AdSense Blog Automation Scheduler Active")
    print("  Schedule: 2 Posts / Week (Tuesday & Friday at 09:00 AM)")
    print("  Target: SQLite (blogs.db) & BlogPost.json & sitemap.xml")
    print("  Press Ctrl+C to stop.")
    print("============================================================\n")

    published_today = False

    while True:
        now = datetime.datetime.now()
        weekday = now.weekday()  # 1 = Tuesday, 4 = Friday
        hour = now.hour

        if weekday in (1, 4) and hour == 9:
            if not published_today:
                print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Triggering scheduled blog post...")
                generate_and_publish_post()
                published_today = True
        else:
            published_today = False

        # Sleep for 1 hour before next check
        time.sleep(3600)


def main():
    parser = argparse.ArgumentParser(description="PrestigePDF Automated Blog Publisher")
    parser.add_argument(
        "--now", action="store_true", help="Generate and publish 1 new AdSense blog post immediately"
    )
    parser.add_argument(
        "--schedule", action="store_true", help="Run 2x/week background publishing schedule"
    )

    args = parser.parse_args()

    if args.now or not sys.argv[1:]:
        print("[Manual Action] Triggering instant blog post generation...")
        generate_and_publish_post()
    elif args.schedule:
        run_scheduler()


if __name__ == "__main__":
    main()

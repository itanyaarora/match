import requests
import time
import logging
from datetime import datetime
import argparse
import os
import json
import hashlib
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ── Constants ──────────────────────────────────────────────────────────────────
# UPDATED: new scale API endpoint
API_URL = "https://rcbscaleapi.ticketgenie.in/ticket/eventlist/O"
CHECK_INTERVAL = 1  # seconds

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')

# PagerDuty configuration
PAGERDUTY_URL = "https://events.pagerduty.com/v2/enqueue"
PAGERDUTY_ROUTING_KEY = os.getenv('PAGERDUTY_ROUTING_KEY')

# State tracking
notification_count = {}   # notifications sent per match (per availability window)
ticket_status = {}        # last known button text per match
last_response_hash = None
last_response_data = None

# ── NEW API field helpers ──────────────────────────────────────────────────────
# The scale API uses these exact keys — centralised here so edits are easy.
def match_id(m):        return m.get('event_Code')
def match_name(m):      return m.get('event_Name', 'Unknown Match')
def match_date_raw(m):  return m.get('event_Date', '')          # "2026-03-28T19:30:00"
def match_date_fmt(m):  return m.get('event_Display_Date', 'N/A')  # "Sat, Mar 28, 2026 07:30 PM"
def match_venue(m):     return m.get('venue_Name', 'N/A')
def match_city(m):      return m.get('city_Name', 'N/A')
def match_price(m):     return m.get('event_Price_Range', 'N/A')
def match_button(m):    return m.get('event_Button_Text', 'Unknown')
def match_team1(m):     return m.get('team_1', '')
def match_team2(m):     return m.get('team_2', '')
def match_group(m):     return m.get('event_Group_Code')        # new field in scale API

TICKET_PAGE = "https://shop.royalchallengers.com/ticket"

def booking_link(m):
    return f"{TICKET_PAGE}?event={match_id(m)}&group={match_group(m)}"

# ── Notification helpers ───────────────────────────────────────────────────────

def send_pagerduty(title, message):
    """Send a critical trigger to PagerDuty."""
    try:
        payload = {
            "payload": {
                "summary": title,
                "severity": "critical",
                "source": message,
            },
            "routing_key": PAGERDUTY_ROUTING_KEY,
            "event_action": "trigger",
        }
        requests.post(PAGERDUTY_URL, json=payload).raise_for_status()
        logging.info("PagerDuty notification sent successfully")
        return True
    except Exception as e:
        logging.error(f"Failed to send PagerDuty notification: {e}")
        return False


def send_telegram(message):
    """Send a message to every configured Telegram chat ID."""
    success = True
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            requests.post(url, json=data).raise_for_status()
        except Exception as e:
            logging.error(f"Failed to send Telegram message to {chat_id}: {e}")
            success = False
    return success


def test_notifications():
    logging.info("Testing notification integrations...")
    msg = (
        "🔍 <b>Notification Integration Test</b>\n\n"
        "If you see this, both integrations are working correctly!\n"
        "You will receive alerts when ticket status changes."
    )
    t = send_telegram(msg)
    p = send_pagerduty("RCB Ticket Monitor Test", "Testing PagerDuty integration")
    logging.info("✅ Telegram test passed" if t else "❌ Telegram test failed")
    logging.info("✅ PagerDuty test passed" if p else "❌ PagerDuty test failed")
    return t and p


# ── Change detection ───────────────────────────────────────────────────────────

def get_response_hash(data):
    """MD5 hash of the full API response for cheap change detection."""
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()


def build_change_summary(old_data, new_data):
    """
    Compare two API snapshots and return a human-readable HTML summary,
    or None if nothing meaningful changed.
    """
    old_results = (old_data or {}).get('result', [])
    new_results = new_data.get('result', [])

    old_map = {match_id(m): m for m in old_results}
    new_map = {match_id(m): m for m in new_results}

    added   = set(new_map) - set(old_map)
    removed = set(old_map) - set(new_map)
    common  = set(old_map) & set(new_map)

    lines = []

    # Whole result list appeared from empty
    if not old_results and new_results:
        lines.append("🆕 <b>Matches have appeared on the API!</b> (was empty before)\n")
        for m in new_results:
            lines.append(
                f"  • <b>{match_name(m)}</b>\n"
                f"    Date: {match_date_fmt(m)}\n"
                f"    Venue: {match_venue(m)}, {match_city(m)}\n"
                f"    Status: {match_button(m)}\n"
                f"    Price: {match_price(m)}"
            )
        return "\n".join(lines)

    # All results disappeared
    if old_results and not new_results:
        return "⚠️ <b>All matches removed from the API!</b> (response is now empty)"

    # New matches added
    if added:
        lines.append(f"🆕 <b>{len(added)} new match(es) added:</b>")
        for code in added:
            m = new_map[code]
            lines.append(
                f"  • <b>{match_name(m)}</b>\n"
                f"    Date: {match_date_fmt(m)}\n"
                f"    Venue: {match_venue(m)}, {match_city(m)}\n"
                f"    Status: {match_button(m)}\n"
                f"    Price: {match_price(m)}"
            )

    # Matches removed
    if removed:
        lines.append(f"❌ <b>{len(removed)} match(es) removed</b>")
        for code in removed:
            m = old_map[code]
            lines.append(f"  • {match_name(m)} ({match_date_fmt(m)})")

    # Field-level changes on existing matches
    # Fields we care about — ignore noisy/cosmetic ones like banners
    WATCHED_FIELDS = {
        'event_Button_Text', 'event_Price_Range', 'event_Display_Date',
        'event_Date', 'venue_Name', 'city_Name', 'event_Name',
        'event_Group_Code',
    }
    for code in common:
        old_m, new_m = old_map[code], new_map[code]
        changes = []
        for key in WATCHED_FIELDS:
            ov, nv = str(old_m.get(key, '')), str(new_m.get(key, ''))
            if ov != nv:
                changes.append(f"    <b>{key}:</b> {ov} → {nv}")
        if changes:
            lines.append(f"🔄 <b>Changes in {match_name(new_m)}:</b>")
            lines.extend(changes)

    return "\n".join(lines) if lines else None


# ── Core polling logic ─────────────────────────────────────────────────────────

def check_api(target_team=None, target_date=None, iteration_count=0):
    """Fetch the Ticket Genie scale API, detect changes, and fire alerts."""
    global last_response_hash, last_response_data

    try:
        logging.info(
            f"🔄 Iteration #{iteration_count} - Checking API" +
            (f" for team: {target_team}" if target_team else
             f" for date: {target_date}" if target_date else
             " for any changes")
        )

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/json',
            # UPDATED: referer matches the scale API's expected origin
            'Origin': 'https://shop.royalchallengers.com',
            'Referer': 'https://shop.royalchallengers.com/',
        }

        response = requests.get(API_URL, headers=headers, timeout=10)

        if response.status_code != 200:
            logging.warning(f"⚠️ API returned status {response.status_code}")
            return

        data = response.json()

        # Validate the outer envelope
        if data.get('status') != 'Success':
            logging.warning(f"⚠️ Unexpected API status: {data.get('status')}")

        logging.info("✅ API response received successfully")

        # ── Full-response change detection ─────────────────────────────────────
        current_hash = get_response_hash(data)

        if last_response_hash is None:
            last_response_hash = current_hash
            last_response_data = data
            logging.info("📸 Baseline response stored (first run)")
        elif current_hash != last_response_hash:
            logging.info("🚨 API RESPONSE HAS CHANGED!")
            summary = build_change_summary(last_response_data, data)
            if summary:
                msg = (
                    f"<b>🚨 RCB API CHANGE DETECTED 🚨</b>\n\n"
                    f"{summary}\n\n"
                    f"<b>🔗 Quick Link:</b>\n"
                    f"• <a href='{TICKET_PAGE}'>RCB Ticket Page</a>"
                )
                send_telegram(msg)
                send_pagerduty(
                    "RCB API Response Changed",
                    f"Change detected at {datetime.now().strftime('%H:%M:%S')}",
                )
            last_response_hash = current_hash
            last_response_data = data
        else:
            logging.info("🔄 No change in API response")
        # ──────────────────────────────────────────────────────────────────────

        matches = data.get('result', [])
        if not matches:
            logging.warning("⚠️ No matches in API response (empty result)")
            return

        logging.info(f"Found {len(matches)} match(es) in response")

        for m in matches:
            # ── Determine if this match is in scope ────────────────────────────
            if not target_team and not target_date:
                in_scope = True
            elif target_team:
                in_scope = (
                    target_team.lower() in match_team1(m).lower() or
                    target_team.lower() in match_team2(m).lower()
                )
                if in_scope:
                    logging.info(f"🎯 Target team match: {match_team1(m)} vs {match_team2(m)}")
            else:
                try:
                    m_date = datetime.strptime(match_date_raw(m), "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")
                    in_scope = (m_date == target_date)
                except ValueError:
                    in_scope = False
                if in_scope:
                    logging.info(f"🎯 Target date match: {match_date_fmt(m)}")

            if not in_scope:
                continue

            mid = match_id(m)
            current_status = match_button(m)
            logging.info(f"Match: {match_name(m)} | Status: {current_status} | Price: {match_price(m)}")

            # Initialise tracking for this match
            if mid not in notification_count:
                notification_count[mid] = 0
                ticket_status[mid] = current_status

            if current_status == 'BUY TICKETS':
                # New availability window — reset counter
                if ticket_status[mid] != 'BUY TICKETS':
                    notification_count[mid] = 0

                ticket_status[mid] = 'BUY TICKETS'

                if notification_count[mid] < 2:
                    logging.info("🎟️ TICKETS AVAILABLE! Sending notification")

                    msg = (
                        f"<b>🚨 RCB TICKETS AVAILABLE! 🚨</b>\n\n"
                        f"<b>Match:</b> {match_name(m)}\n"
                        f"<b>Date:</b> {match_date_fmt(m)}\n"
                        f"<b>Venue:</b> {match_venue(m)}, {match_city(m)}\n"
                        f"<b>Price Range:</b> {match_price(m)}\n\n"
                        f"<b>🔗 Quick Links:</b>\n"
                        f"• <a href='{booking_link(m)}'>Book Tickets Now</a>\n"
                        f"• <a href='{TICKET_PAGE}'>RCB Ticket Page</a>"
                    )

                    t_ok = send_telegram(msg)
                    p_ok = send_pagerduty(
                        f"RCB Tickets Available – {match_name(m)}",
                        f"Tickets on sale for {match_name(m)} on {match_date_fmt(m)}",
                    )

                    if t_ok and p_ok:
                        notification_count[mid] += 1
                        logging.info(f"✅ Notification sent ({notification_count[mid]}/2)")
                    else:
                        logging.error("❌ One or more notifications failed")
                else:
                    logging.info(
                        f"🔔 Already sent {notification_count[mid]} notifications "
                        f"for this availability window — suppressing further alerts"
                    )
            else:
                if ticket_status[mid] == 'BUY TICKETS':
                    logging.info("🚫 Tickets no longer available — will re-alert if they open again")
                ticket_status[mid] = current_status

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Network error: {e}")
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='RCB Ticket Genie Scale API Monitor')
    parser.add_argument('--team', help='Team name to monitor (e.g. "Sunrisers Hyderabad")')
    parser.add_argument('--date', help='Match date to monitor (YYYY-MM-DD)')
    parser.add_argument('--test', action='store_true', help='Send test notifications and exit')
    args = parser.parse_args()

    if args.test:
        logging.info("🧪 Running in test mode")
        test_notifications()
        return

    start_time = datetime.now()
    iteration_count = 0

    if args.team:
        mode_msg = f"Monitoring matches with <b>{args.team}</b>"
    elif args.date:
        mode_msg = f"Monitoring match on <b>{args.date}</b>"
    else:
        mode_msg = "Monitoring <b>ALL</b> changes to the RCB Ticket Genie API"

    logging.info(f"🎯 Starting monitor — {mode_msg.replace('<b>', '').replace('</b>', '')}")
    send_telegram(f"🔄 RCB Ticket Monitor is running!\n\n{mode_msg}")

    while True:
        try:
            iteration_count += 1
            runtime = datetime.now() - start_time
            logging.info(
                f"📊 Runtime: {runtime} | Iterations: {iteration_count} | "
                f"Next check in {CHECK_INTERVAL}s"
            )
            check_api(args.team, args.date, iteration_count)
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logging.info("👋 Stopped by user")
            send_telegram("🛑 RCB Ticket Monitor stopped by user")
            break
        except Exception as e:
            logging.error(f"❌ Critical error in main loop: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()

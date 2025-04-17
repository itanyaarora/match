import requests
import time
import logging
from datetime import datetime
import argparse
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Constants
API_URL = "https://rcbmpapi.ticketgenie.in/ticket/eventlist/O"
CHECK_INTERVAL = 1  # Check every 1 second
# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')

# PagerDuty configuration
PAGERDUTY_URL = "https://events.pagerduty.com/v2/enqueue"
PAGERDUTY_ROUTING_KEY = os.getenv('PAGERDUTY_ROUTING_KEY')

def send_pagerduty(title, message):
    """Send notification to PagerDuty"""
    try:
        payload = {
            "payload": {
                "summary": title,
                "severity": "critical",
                "source": message
            },
            "routing_key": PAGERDUTY_ROUTING_KEY,
            "event_action": "trigger"
        }
        response = requests.post(PAGERDUTY_URL, json=payload)
        response.raise_for_status()
        logging.info("PagerDuty notification sent successfully")
        return True
    except Exception as e:
        logging.error(f"Failed to send PagerDuty notification: {str(e)}")
        return False

def send_telegram(message):
     """Send message to all Telegram recipients"""
     success = True
     for chat_id in TELEGRAM_CHAT_IDS:
         try:
             url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
             data = {
                 "chat_id": chat_id,
                 "text": message,
                 "parse_mode": "HTML",
                 "disable_web_page_preview": True
             }
             requests.post(url, json=data).raise_for_status()
         except Exception as e:
             logging.error(f"Failed to send Telegram message to {chat_id}: {str(e)}")
             success = False
     return success

def test_notifications():
    logging.info("Testing notification integrations...")
    test_message = (
        "🔍 <b>Notification Integration Test</b>\n\n"
        "If you see this message, both Telegram and PagerDuty integrations are working correctly!\n"
        "You will receive notifications when tickets become available."
    )

    telegram_success = send_telegram(test_message)
    pagerduty_success = send_pagerduty("RCB Ticket Monitor Test", "Testing PagerDuty integration")

    if telegram_success:
        logging.info("✅ Telegram test successful")
    else:
        logging.error("❌ Telegram test failed")

    if pagerduty_success:
        logging.info("✅ PagerDuty test successful")
    else:
        logging.error("❌ PagerDuty test failed")

    return telegram_success and pagerduty_success

def check_api(target_team=None, target_date=None, iteration_count=0):
    """Check the RCB API and log the response"""
    try:
        logging.info(f"🔄 Iteration #{iteration_count} - Checking API for {'team: ' + target_team if target_team else 'date: ' + target_date}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Origin': 'https://shop.royalchallengers.com',
            'Referer': 'https://shop.royalchallengers.com/'
        }

        logging.debug(f"Making request to {API_URL}")
        response = requests.get(API_URL, headers=headers)

        if response.status_code != 200:
            logging.warning(f"⚠️ API returned status code: {response.status_code}")
            return

        data = response.json()
        logging.info(f"✅ API response received successfully")

        if not data.get('result'):
            logging.warning("⚠️ No matches found in API response")
            return

        matches = data['result']
        logging.info(f"Found {len(matches)} total matches in response")

        for match in matches:
            # Check if this is our target match
            is_target_match = False

            if target_team:
                is_target_match = (target_team.lower() in match['team_1'].lower() or
                                 target_team.lower() in match['team_2'].lower())
                if is_target_match:
                    logging.info(f"🎯 Found target team match: {match['team_1']} vs {match['team_2']}")
            elif target_date:
                match_date = datetime.strptime(match['event_Date'], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")
                is_target_match = match_date == target_date
                if is_target_match:
                    logging.info(f"🎯 Found target date match: {match['event_Display_Date']}")

            if is_target_match:
                logging.info(f"Match Status: {match.get('event_Button_Text', 'Unknown')}")

                if match.get('event_Button_Text') == 'BUY TICKETS':
                    logging.info("🎟️ TICKETS AVAILABLE!")
                    booking_link = f"https://shop.royalchallengers.com/ticket?event={match['event_Code']}"

                    message = (
                        f"<b>🚨 RCB MATCH TICKETS AVAILABLE! 🚨</b>\n\n"
                        f"<b>Match:</b> {match['event_Name']}\n"
                        f"<b>Date:</b> {match['event_Display_Date']}\n"
                        f"<b>Venue:</b> {match['venue_Name']}, {match['city_Name']}\n"
                        f"<b>Price Range:</b> {match['event_Price_Range']}\n\n"
                        f"<b>Quick Links:</b>\n"
                        f"• <a href='{booking_link}'>Book Tickets Now</a>\n"
                        f"• <a href='https://shop.royalchallengers.com/ticket'>RCB Ticket Page</a>"
                    )

                    telegram_success = send_telegram(message)
                    pagerduty_success = send_pagerduty(
                        f"RCB Tickets Available - {match['event_Name']}",
                        f"Tickets available for {match['event_Name']} on {match['event_Display_Date']}"
                    )

                    if telegram_success and pagerduty_success:
                        logging.info("✅ Notifications sent successfully!")
                    else:
                        logging.error("❌ Some notifications failed to send")

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Network error occurred: {str(e)}")
    except Exception as e:
        logging.error(f"❌ Unexpected error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='RCB Ticket API Checker')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--team', help='Team to monitor (e.g., "Delhi Capitals")')
    group.add_argument('--date', help='Date to monitor (format: YYYY-MM-DD)')
    parser.add_argument('--test', action='store_true', help='Test notifications only')
    args = parser.parse_args()

    if args.test:
        logging.info("🧪 Running in test mode")
        test_notifications()
        return

    start_time = datetime.now()
    iteration_count = 0

    if args.team:
        logging.info(f"🎯 Starting RCB API Checker - Monitoring matches with {args.team}")
        send_telegram(f"🔄 RCB Ticket Monitor is running!\n\nMonitoring tickets for match against {args.team}")
    else:
        logging.info(f"🎯 Starting RCB API Checker - Monitoring match on {args.date}")
        send_telegram(f"🔄 RCB Ticket Monitor is running!\n\nMonitoring tickets for match on {args.date}")

    while True:
        try:
            iteration_count += 1
            current_time = datetime.now()
            runtime = current_time - start_time

            logging.info("📊 Status Update:")
            logging.info(f"  • Runtime: {runtime}")
            logging.info(f"  • Total Iterations: {iteration_count}")
            logging.info(f"  • Next check in {CHECK_INTERVAL} seconds")

            check_api(args.team, args.date, iteration_count)

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logging.info("👋 Stopped by user")
            send_telegram("🛑 RCB Ticket Monitor stopped by user")
            break
        except Exception as e:
            logging.error(f"❌ Critical error in main loop: {str(e)}")
            logging.info(f"⏳ Waiting {CHECK_INTERVAL} seconds before retrying...")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    test_notifications()
    main()

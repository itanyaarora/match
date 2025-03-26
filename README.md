# RCB Ticket Monitor

A Python script to monitor RCB match tickets and send notifications via Telegram and PagerDuty when tickets become available.

## Features

- Monitors RCB match tickets for specific teams or dates
- Sends notifications via Telegram and PagerDuty
- Configurable check interval
- Support for monitoring multiple matches
- Detailed logging

## Prerequisites

- Python 3.7 or higher
- Telegram Bot Token
- PagerDuty Routing Key
- Required Python packages (see requirements.txt)

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/rcb-ticket-monitor.git
cd rcb-ticket-monitor
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your credentials:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_IDS=chat_id1,chat_id2
PAGERDUTY_ROUTING_KEY=your_pagerduty_routing_key
```

## Usage

### Monitor tickets for a specific team:
```bash
python rcb_api_checker.py --team "Delhi Capitals"
```

### Monitor tickets for a specific date:
```bash
python rcb_api_checker.py --date "2025-05-03"
```

### Test notifications:
```bash
python rcb_api_checker.py --test
```

### Run in background:
```bash
./run_monitor.sh
```

### Stop the monitor:
```bash
./stop_monitor.sh
```

## Configuration

- `CHECK_INTERVAL`: Time between API checks (default: 30 seconds)
- `API_URL`: RCB ticket API endpoint
- Telegram and PagerDuty configurations in `.env` file

## Logging

Logs are stored in the `logs` directory with timestamps. Each log file contains:
- API responses
- Notification status
- Error messages
- Start/stop events

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

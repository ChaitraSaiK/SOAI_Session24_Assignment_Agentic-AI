# SAgentic AI - Smart Calendar Assistant - AI-Powered Event Notifications

![Agentic AI](https://img.shields.io/badge/Agentic%20AI-Enabled-brightgreen)
![Gemini LLM](https://img.shields.io/badge/Gemini%20LLM-API-blue)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-green)
![Google Calendar](https://img.shields.io/badge/Google%20Calendar-API-orange)
![Chrome Extension](https://img.shields.io/badge/Chrome-Extension-yellow)

This application integrates Google Calendar, Gemini LLM, and Telegram to provide smart notifications about your upcoming calendar events.

## Features

- Fetches events from Google Calendar
- Processes events using Gemini LLM for intelligent analysis
- Sends notifications to Telegram
- Chrome extension for easy access

## Setup Instructions

### 1. Environment Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your credentials:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
GEMINI_API_KEY=your_gemini_api_key
```

### 2. Google Calendar Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Google Calendar API
4. Create OAuth 2.0 credentials
5. Download the credentials and save as `credentials.json` in the project root

### 3. Telegram Setup

1. Create a new bot using [@BotFather](https://t.me/botfather) on Telegram
2. Get your bot token and chat ID
3. Add these to your `.env` file

### 4. Chrome Extension Setup

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" and select the `chrome_extension` directory

## Running the Application

1. Start the FastAPI server:
```bash
uvicorn main:app --reload
```

2. The server will be available at `http://localhost:8000`

3. Use the Chrome extension to fetch and process calendar events

## API Endpoints

- `POST /process-events`: Process calendar events for a specified number of days
- `GET /health`: Health check endpoint

## Chrome Extension Usage

1. Click the extension icon in your Chrome browser
2. Select the time period (5, 10, or 15 days)
3. The events will be processed and sent to your Telegram
4. Type any question and LLM will generate answer which will be sent to your Telegram

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- In production, use proper CORS settings and HTTPS
- Store credentials securely 
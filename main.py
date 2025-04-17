from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import sys
from datetime import datetime, timedelta
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
import telegram
import os
import pickle
from dotenv import load_dotenv
import asyncio
import json
from typing import List, Dict
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TOKEN_FILE = 'token.pickle'

# Initialize Gemini
try:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found in environment variables")
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    
    # Configure Gemini with specific settings
    genai.configure(
        api_key=GEMINI_API_KEY,
        transport="rest"  # Ensure we're using REST transport
    )
    
    # List available models first
    logger.info("Checking available models...")
    available_models = genai.list_models()
    logger.info(f"Available models: {[model.name for model in available_models]}")
    
    # Initialize the model with generation config
    generation_config = {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 40,
        "max_output_tokens": 2048
    }
    
    # Try to initialize the model
    MODEL_NAME = "models/gemini-1.5-pro"  # Use the full model name that's available
    logger.info(f"Attempting to initialize model: {MODEL_NAME}")
    model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)
    
    # Test the model
    logger.info("Testing Gemini API with a simple prompt...")
    try:
        test_response = model.generate_content("Test message")
        if test_response and test_response.text:
            logger.info(f"Gemini API test successful. Response: {test_response.text}")
        else:
            raise ValueError("Empty response from Gemini API")
    except Exception as e:
        logger.error(f"Error testing Gemini model: {str(e)}")
        raise

except ValueError as ve:
    logger.error(f"Validation error with Gemini API: {str(ve)}")
    model = None
    logger.warning("Will continue without LLM capabilities - falling back to basic event summaries")
except Exception as e:
    logger.error(f"Unexpected error initializing Gemini API: {str(e)}")
    model = None
    logger.warning("Will continue without LLM capabilities - falling back to basic event summaries")

# Initialize Telegram bot
bot = telegram.Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))

# Add after imports
llm_call_counter = 0

# Add conversation history storage
class ConversationManager:
    def __init__(self):
        self.conversations: Dict[str, List[Dict]] = {}  # user_id -> conversation history
        self.max_history = 10  # Maximum number of interactions to keep
        
    def add_interaction(self, user_id: str, role: str, content: str):
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        self.conversations[user_id].append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
        
        # Keep only the last max_history interactions
        if len(self.conversations[user_id]) > self.max_history:
            self.conversations[user_id] = self.conversations[user_id][-self.max_history:]
    
    def get_conversation(self, user_id: str) -> str:
        if user_id not in self.conversations:
            return ""
        
        return "\n\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in self.conversations[user_id]
        ])
    
    def clear_conversation(self, user_id: str):
        if user_id in self.conversations:
            del self.conversations[user_id]

# Initialize conversation manager
conversation_manager = ConversationManager()

def get_google_calendar_service(token: str):
    """Get Google Calendar service with credentials"""
    logger.info("Getting Google Calendar service")
    try:
        creds = Credentials(token=token)
        logger.info("Building calendar service")
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Error creating service: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

async def get_calendar_events(service, days: int):
    """Fetch calendar events for the next N days"""
    logger.info(f"Fetching calendar events for next {days} days")
    
    now = datetime.utcnow().isoformat() + 'Z'
    end_time = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'
    
    logger.info(f"Fetching events from {now} to {end_time}")
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        timeMax=end_time,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    logger.info(f"Found {len(events)} events")
    return events

async def process_events_with_llm(events):
    """Process events with Gemini LLM"""
    global llm_call_counter
    logger.info("Processing events with LLM")
    
    # First, generate the basic summary with icons
    basic_summary = generate_basic_summary(events)
    
    if model is None:
        logger.warning("LLM not available - using basic summary only")
        return basic_summary
        
    max_retries = 3
    base_delay = 6  # Starting delay in seconds
    
    for attempt in range(max_retries):
        try:
            events_text = "\n".join([
                f"Event: {event['summary']}\n"
                f"Time: {event['start'].get('dateTime', event['start'].get('date'))} to "
                f"{event['end'].get('dateTime', event['end'].get('date'))}\n"
                f"Description: {event.get('description', 'No description')}\n"
                for event in events
            ])
            
            prompt = f"""Analyze these calendar events and provide a summary:
            {events_text}
            
            Please provide a concise summary highlighting:
            1. Key events and their importance
            2. Important timing information
            3. Any potential conflicts or tight schedules
            4. Suggestions for preparation
            
            Format the response in a clear, readable way.
            """
            
            logger.info(f"Generating response from LLM (attempt {attempt + 1}/{max_retries})")
            response = model.generate_content(prompt)
            llm_call_counter += 1
            logger.info(f"Total LLM calls made: {llm_call_counter}")
            
            if not response or not response.text:
                raise ValueError("Empty response from Gemini API")
            
            # Combine basic summary with LLM analysis
            combined_summary = (
                f"{basic_summary}\n"
                f"<b>🤖 AI Analysis:</b>\n\n"
                f"{response.text}\n"
            )
            
            return combined_summary
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error processing with LLM: {error_str}")
            
            # Check if it's a rate limit error
            if "429" in error_str and "quota" in error_str.lower():
                if attempt < max_retries - 1:  # Don't wait on last attempt
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Rate limit hit. Waiting {delay} seconds before retry...")
                    await asyncio.sleep(delay)
                    continue
            
            # For non-rate-limit errors or if we've exhausted retries
            return basic_summary
            
    # If we've exhausted all retries
    logger.warning("Exhausted all retries for LLM. Falling back to basic summary")
    return basic_summary

def generate_basic_summary(events):
    """Generate a basic summary without LLM"""
    if not events:
        return "🗓 No upcoming events found in the specified period."
        
    summary = "<b>YOUR UPCOMING EVENTS</b>\n\n"
    
    # Sort events by start time
    sorted_events = sorted(events, key=lambda x: x['start'].get('dateTime', x['start'].get('date')))
    
    for event in sorted_events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        
        # Format the event block with simple icons
        summary += f"<b>{event['summary']}</b>\n"  # Event title in bold
        
        # Format date
        date = start.split('T')[0] if 'T' in start else start
        summary += f"🗓 {date}\n"
        
        # Add time if it's not an all-day event
        if 'T' in start:
            start_time = start.split('T')[1].split('+')[0][:5]  # Get HH:MM
            end_time = end.split('T')[1].split('+')[0][:5]  # Get HH:MM
            summary += f"⏰ {start_time} - {end_time}\n"
        
        # Add location if available
        if 'location' in event and event['location']:
            summary += f"📍 {event['location']}\n"
            
        # Add description if available
        if 'description' in event and event['description']:
            desc = event['description'].replace('\n', ' ').strip()
            if len(desc) > 100:  # Truncate long descriptions
                desc = desc[:97] + "..."
            summary += f"📝 {desc}\n"
            
        # Add a simple separator between events
        summary += "\n───────────\n\n"
    
    return summary

async def send_telegram_message(message):
    """Send message to Telegram"""
    logger.info("Sending message to Telegram")
    # Use HTML parsing instead of Markdown
    await bot.send_message(
        chat_id=os.getenv('TELEGRAM_CHAT_ID'),
        text=message,
        parse_mode='HTML'
    )
    logger.info("Message sent successfully")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check requested")
    return {"status": "healthy"}

@app.post("/process-events")
async def process_events(request: FastAPIRequest):
    """Process calendar events and send notification"""
    logger.info("Received process-events request")
    
    try:
        # Get request data
        data = await request.json()
        days = data.get('days', 7)
        token = data.get('token')  # Change back to token
        
        if not token:
            logger.error("No token provided in request")
            raise HTTPException(status_code=400, detail="No token provided")
            
        # Get calendar service with token
        service = get_google_calendar_service(token)
        
        # Get calendar events using the service
        events = await get_calendar_events(service, days)
        logger.info(f"Retrieved {len(events)} events")
        
        if not events:
            logger.info("No events found")
            return {"status": "success", "message": "No events found in the specified period"}
        
        summary = await process_events_with_llm(events)
        logger.info(f"Current LLM call count: {llm_call_counter}")
        
        # Send to Telegram
        await send_telegram_message(summary)
        logger.info("Notification sent to Telegram")
        
        return {
            "status": "success",
            "message": "Events processed and notification sent",
            "summary": summary
        }
        
    except HTTPException as e:
        logger.error(f"HTTP error processing events: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Error processing events: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth")
async def auth():
    """Handle Google Calendar authentication"""
    logger.info("Starting authentication process")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        logger.info("Getting authorization URL")
        auth_url, _ = flow.authorization_url(prompt='consent')
        logger.info(f"Generated auth URL: {auth_url}")
        return {"auth_url": auth_url}
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/callback")
async def auth_callback(code: str):
    """Handle OAuth callback"""
    logger.info("Received OAuth callback")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        logger.info("Fetching token")
        flow.fetch_token(code=code)
        creds = flow.credentials
        logger.info("Saving credentials")
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
        logger.info("Authentication successful")
        return {"message": "Successfully authenticated with Google Calendar!"}
    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask-llm")
async def ask_llm_question(request: FastAPIRequest):
    """Ask LLM questions about calendar events with conversation history"""
    logger.info("Received question for LLM")
    
    try:
        # Get request data
        data = await request.json()
        question = data.get('question')
        token = data.get('token')
        days = data.get('days', 7)
        user_id = data.get('user_id', 'default')  # Identify different users
        
        if not question:
            raise HTTPException(status_code=400, detail="No question provided")
        if not token:
            raise HTTPException(status_code=400, detail="No token provided")
            
        # Get calendar service with token
        service = get_google_calendar_service(token)
        
        # Get calendar events
        events = await get_calendar_events(service, days)
        logger.info(f"Retrieved {len(events)} events for analysis")
        
        # Format events for LLM
        events_text = "\n".join([
            f"Event: {event['summary']}\n"
            f"Time: {event['start'].get('dateTime', event['start'].get('date'))} to "
            f"{event['end'].get('dateTime', event['end'].get('date'))}\n"
            f"Description: {event.get('description', 'No description')}\n"
            for event in events
        ])
        
        # Get conversation history
        conversation_history = conversation_manager.get_conversation(user_id)
        
        # Create prompt with conversation history and new question
        prompt = f"""Here are your calendar events:
        {events_text}
        
        Previous conversation:
        {conversation_history}
        
        New question: {question}
        
        Please provide a helpful and specific answer based on:
        1. The calendar events provided
        2. Our previous conversation context
        3. Any relevant information from past interactions
        
        Answer the question directly and clearly.
        """
        
        if model is None:
            raise HTTPException(status_code=503, detail="LLM service not available")
            
        # Get response from LLM
        try:
            response = model.generate_content(prompt)
            if not response or not response.text:
                raise ValueError("Empty response from LLM")
            
            # Store the interaction in conversation history
            conversation_manager.add_interaction(user_id, "user", question)
            conversation_manager.add_interaction(user_id, "assistant", response.text)
                
            # Format the response for Telegram
            telegram_message = (
                f"<b>❓ Question:</b>\n{question}\n\n"
                f"<b>🤖 Answer:</b>\n{response.text}"
            )
            
            # Send to Telegram
            await send_telegram_message(telegram_message)
            
            return {
                "status": "success",
                "message": "Question answered and sent to Telegram",
                "answer": response.text,
                "conversation_history": conversation_manager.get_conversation(user_id)
            }
            
        except Exception as e:
            logger.error(f"Error getting LLM response: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error getting LLM response: {str(e)}")
            
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error processing question: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add endpoint to clear conversation history
@app.post("/clear-conversation")
async def clear_conversation(request: FastAPIRequest):
    """Clear conversation history for a user"""
    data = await request.json()
    user_id = data.get('user_id', 'default')
    conversation_manager.clear_conversation(user_id)
    return {"status": "success", "message": "Conversation history cleared"}

if __name__ == "__main__":
    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info") 
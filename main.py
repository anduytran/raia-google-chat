import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import google.auth
from googleapiclient.discovery import build

app = FastAPI()

# Set up logging to see errors in Cloud Run
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# authenticate with Google (Cloud Run does this automatically)
SCOPES = ['https://www.googleapis.com/auth/chat.bot']
credentials, project_id = google.auth.default(scopes=SCOPES)
chat_service = build('chat', 'v1', credentials=credentials)

@app.get("/")
def check_health():
    return {"status": "alive", "version": "0.0.3"}

@app.post("/")
async def receive_chat_event(request: Request):
    try:
        event = await request.json()
        logger.info(f"FULL EVENT RECEIVED: {event}")
    except Exception as e:
        logger.error(f"JSON Parse Error: {e}")
        return JSONResponse(content={"error": "invalid json"}, status_code=400)

    # 1. Check if it's a message event
    if 'chat' in event and 'messagePayload' in event['chat']:
        payload = event['chat']['messagePayload']
        space_name = payload['space']['name'] # e.g. "spaces/AAAA..."
        user_name = payload['message']['sender']['displayName']
        user_message = payload['message']['text']
        
        logger.info(f"User: {user_name} said: {user_message}")

        # 2. SEND MESSAGE VIA API (The link you found)
        try:
            msg_text = f"Async Reply: I heard you, {user_name}!"
            
            # Call spaces.messages.create
            chat_service.spaces().messages().create(
                parent=space_name,
                body={'text': msg_text}
            ).execute()
            
            logger.info("Message sent successfully via API!")

        except Exception as api_error:
            # THIS is where we will finally see the real error if it fails
            logger.error(f"API CALL FAILED: {api_error}")

    elif event.get('type') == 'MESSAGE':
        # Fallback for legacy events
        space_name = event['space']['name']
        try:
            chat_service.spaces().messages().create(
                parent=space_name,
                body={'text': "Legacy Async Reply!"}
            ).execute()
        except Exception as e:
            logger.error(f"Legacy API Error: {e}")

    # 3. Return EMPTY JSON to stop the "Bot not responding" error
    # This tells Google "I received the event, you can stop waiting."
    return {}
import os
import logging
import hashlib
import re
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import google.auth
from googleapiclient.discovery import build

# --- CONFIGURATION ---
# Ensure this is set in your Cloud Run "Variables"
RAIA_API_KEY = os.getenv("RAIA_API_KEY") 
RAIA_BASE_URL = "https://api.raia2.com/external"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- GOOGLE CHAT AUTH ---
SCOPES = ['https://www.googleapis.com/auth/chat.bot']
credentials, project_id = google.auth.default(scopes=SCOPES)
chat_service = build('chat', 'v1', credentials=credentials)

# --- HELPER FUNCTIONS ---

def normalize_text(text: str) -> str:
    """Strips mentions and cleans whitespace."""
    if not text: return ""
    # Removes <users/1234> pattern
    text = re.sub(r'<users/[^>]+>', '', text)
    return text.strip()

def generate_deterministic_key(space_name: str, user_name: str) -> str:
    """Generates a consistent key based on the User and Space."""
    # This ensures the same user in the same DM always gets the same Raia history
    raw_key = f"{space_name}:{user_name}"
    return hashlib.sha256(raw_key.encode()).hexdigest()

async def get_active_raia_conversation(external_key: str, user_display_name: str) -> str:
    """
    1. Tries to find an existing open conversation for this user key.
    2. If none exists, creates a new one.
    """
    headers = {
        "Content-Type": "application/json",
        "Agent-Secret-Key": RAIA_API_KEY
    }

    async with httpx.AsyncClient() as client:
        # STEP 1: Search for existing active conversation
        # We filter by 'fkUserId' to resume the correct user's history
        try:
            search_response = await client.get(
                f"{RAIA_BASE_URL}/conversations",
                params={"fkUserId": external_key, "status": "open"}, 
                headers=headers,
                timeout=5.0
            )
            
            if search_response.status_code == 200:
                data = search_response.json()
                # Raia returns a list of conversations. We take the most recent one.
                # Adjust depending on actual response structure (e.g. data['items'] vs data)
                conversations = data if isinstance(data, list) else data.get('items', [])
                
                if conversations:
                    # Assuming the first one is the most relevant/recent
                    existing_id = conversations[0].get('id') or conversations[0].get('conversationId')
                    logger.info(f"Resuming Raia conversation: {existing_id}")
                    return existing_id

        except Exception as e:
            logger.warning(f"Lookup failed (creating new instead): {e}")

        # STEP 2: Start new conversation if lookup failed or returned empty
        logger.info(f"Starting NEW conversation for key: {external_key[:8]}")
        
        start_payload = {
            "channel": "api", 
            "fkUserId": external_key,
            "firstName": user_display_name,
            "context": "User connected via Google Chat integration."
        }
        
        # POST /conversations/start
        start_response = await client.post(
            f"{RAIA_BASE_URL}/conversations/start",
            json=start_payload,
            headers=headers,
            timeout=10.0
        )
        start_response.raise_for_status()
        start_data = start_response.json()
        
        # Raia returns the new ID
        new_id = start_data.get("conversationId") or start_data.get("id")
        return new_id

async def send_message_to_raia(conversation_id: str, message: str) -> str:
    """Sends the user message to Raia and returns the Agent's text response."""
    headers = {
        "Content-Type": "application/json",
        "Agent-Secret-Key": RAIA_API_KEY
    }
    
    payload = {
        "text": message
    }

    async with httpx.AsyncClient() as client:
        try:
            # POST /conversations/{id}/messages
            response = await client.post(
                f"{RAIA_BASE_URL}/conversations/{conversation_id}/messages",
                json=payload,
                headers=headers,
                timeout=45.0 # Increased timeout as AI generation can be slow
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract text from response (handling potential variations)
            return data.get("text") or data.get("message") or "..."

        except httpx.HTTPStatusError as e:
            logger.error(f"Raia API Error {e.response.status_code}: {e.response.text}")
            return "I'm having trouble connecting to the AI Agent right now."
        except Exception as e:
            logger.error(f"Connection Error: {e}")
            return "I'm having trouble reaching the AI Agent."

# --- MAIN ENDPOINT ---

@app.post("/")
async def receive_chat_event(request: Request):
    try:
        event = await request.json()
    except Exception:
        return JSONResponse(content={"error": "invalid json"}, status_code=400)

    # Check for MESSAGE event
    if 'chat' in event and 'messagePayload' in event['chat']:
        payload = event['chat']['messagePayload']
        space_name = payload['space']['name']
        user_name = payload['message']['sender']['name']
        user_display = payload['message']['sender']['displayName']
        raw_text = payload['message']['text']
        
        # 1. Normalize
        clean_text = normalize_text(raw_text)
        
        # If text is empty (e.g. just an image), ignore or handle gracefully
        if not clean_text:
            return {}

        # 2. Generate Key
        external_key = generate_deterministic_key(space_name, user_name)

        # 3. Async Processing (Fire-and-forget logic)
        async def process_and_reply():
            try:
                # A. Get Context
                raia_id = await get_active_raia_conversation(external_key, user_display)
                
                # B. Get AI Reply
                agent_reply = await send_message_to_raia(raia_id, clean_text)
                
                # C. Reply to Google Chat
                chat_service.spaces().messages().create(
                    parent=space_name,
                    body={'text': agent_reply}
                ).execute()
                
            except Exception as e:
                logger.error(f"Pipeline Error: {e}")
                # Optional: Send generic error card to user if desired

        # Execute async
        await process_and_reply()

    # Always acknowledge receipt immediately
    return {}
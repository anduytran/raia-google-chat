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
    2. If none, Ensure User Exists -> Create New Generic Conversation.
    """
    headers = {
        "Content-Type": "application/json",
        "Agent-Secret-Key": RAIA_API_KEY
    }

    async with httpx.AsyncClient() as client:
        # STEP 1: Search for existing active conversation (Unchanged)
        try:
            search_response = await client.get(
                f"{RAIA_BASE_URL}/conversations",
                params={"fkUserId": external_key, "status": "open"}, 
                headers=headers,
                timeout=5.0
            )
            
            if search_response.status_code == 200:
                data = search_response.json()
                conversations = data if isinstance(data, list) else data.get('items', [])
                if conversations:
                    return conversations[0].get('id') or conversations[0].get('conversationId')
        except Exception as e:
            logger.warning(f"Lookup failed: {e}")

        # STEP 2: The New Strategy (Create User -> Create Conversation)
        logger.info(f"Creating NEW generic conversation for key: {external_key[:8]}")

        # A. Create or Get the User first
        # We try to create the user. If they exist, Raia usually returns the existing ID or we can search.
        name_parts = user_display_name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else "User"
        
        user_payload = {
            "fkId": external_key,
            "firstName": first_name,
            "lastName": last_name
        }
        
        # We attempt to create the user to get their internal ID
        user_response = await client.post(
            f"{RAIA_BASE_URL}/users",
            json=user_payload,
            headers=headers,
            timeout=10.0
        )
        
        if user_response.status_code == 200 or user_response.status_code == 201:
            user_data = user_response.json()
            raia_user_id = user_data.get("id")
        else:
            # If creation fails (maybe user exists?), try to search for them
            logger.info("User creation failed/existed, searching instead...")
            search_user = await client.get(
                f"{RAIA_BASE_URL}/users/search",
                params={"fkId": external_key},
                headers=headers
            )
            search_user.raise_for_status()
            user_data = search_user.json()
            # Handle list vs object return
            if isinstance(user_data, list) and user_data:
                raia_user_id = user_data[0].get("id")
            else:
                raia_user_id = user_data.get("id")

        if not raia_user_id:
            raise ValueError("Could not get Raia User ID")

        # B. Create the Conversation using the internal User ID
        # This matches the screenshot you sent (POST /external/conversations)
        create_conv_payload = {
            "conversationUserId": raia_user_id,
            "title": f"Chat with {first_name}",
            "context": "User connected via Google Chat."
        }
        
        create_response = await client.post(
            f"{RAIA_BASE_URL}/conversations",
            json=create_conv_payload,
            headers=headers,
            timeout=10.0
        )
        
        if create_response.status_code >= 400:
            logger.error(f"Raia Create Error: {create_response.text}")
            
        create_response.raise_for_status()
        new_data = create_response.json()
        
        return new_data.get("conversationId") or new_data.get("id")

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
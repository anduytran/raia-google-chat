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

def generate_deterministic_key(space_name: str, user_name: str, space_type: str, thread_name: str = None) -> str:
    """
    Generates a consistent key based on the context.
    - DMs (DIRECT_MESSAGE): Tied to the specific user.
    - Spaces (ROOM): Tied to the specific thread, so multiple users share context.
    """
    if space_type == "DIRECT_MESSAGE":
        raw_key = f"{space_name}:{user_name}"
    else:
        # In a group space, use the thread name. If no thread (rare but possible), default to space.
        # This groups all users in a thread into a single Raia conversation.
        raw_key = thread_name if thread_name else space_name
        
    return hashlib.sha256(raw_key.encode()).hexdigest()

async def get_active_raia_conversation(external_key: str, user_display_name: str) -> str:
    """
    1. Searches for the user to retrieve their existing conversation history.
    2. If a conversation exists, returns the latest one to continue the chat.
    3. If not, creates the user (if needed) and a new conversation.
    """
    headers = {
        "Content-Type": "application/json",
        "Agent-Secret-Key": RAIA_API_KEY
    }

    async with httpx.AsyncClient() as client:
        raia_user_id = None

        # STEP 1: Search for the User and their Conversation History
        try:
            search_user = await client.get(
                f"{RAIA_BASE_URL}/users/search",
                params={"fkId": external_key},
                headers=headers,
                timeout=5.0
            )
            
            if search_user.status_code == 200:
                user_data = search_user.json()
                
                # Check if we got valid data back (not an empty list)
                if user_data:
                    # Handle list vs object return safely
                    record = user_data[0] if isinstance(user_data, list) else user_data
                    
                    # Extract the internal Raia User ID
                    raia_user_id = record.get("user", {}).get("id") or record.get("id")
                    
                    # Extract existing conversations!
                    conv_ids = record.get("conversationIds", [])
                    if conv_ids and isinstance(conv_ids, list):
                        # Pick the most recent conversation to continue
                        latest_conv_id = conv_ids[-1]
                        logger.info(f"Continuing existing conversation: {latest_conv_id}")
                        return latest_conv_id

        except Exception as e:
            logger.warning(f"User search/history check failed: {e}")

        # STEP 2: Create User (Only if they weren't found in Step 1)
        name_parts = user_display_name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else "User"

        if not raia_user_id:
            logger.info(f"Creating new user for key: {external_key[:8]}")
            user_payload = {
                "fkId": external_key,
                "firstName": first_name,
                "lastName": last_name
            }
            
            user_response = await client.post(
                f"{RAIA_BASE_URL}/users",
                json=user_payload,
                headers=headers,
                timeout=10.0
            )
            user_response.raise_for_status()
            
            # Extract the newly created ID
            new_user_data = user_response.json()
            raia_user_id = new_user_data.get("user", {}).get("id") or new_user_data.get("id")
            
            if not raia_user_id:
                raise ValueError("Could not get or create Raia User ID")

        # STEP 3: Create a NEW Conversation (Since no history was found)
        logger.info(f"Creating NEW conversation for user: {raia_user_id}")
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
        "message": str(message)
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
        space_type = payload['space'].get('type', 'DIRECT_MESSAGE') # DIRECT_MESSAGE or ROOM
        user_name = payload['message']['sender']['name']
        user_display = payload['message']['sender']['displayName']
        raw_text = payload['message']['text']
        
        # Safely extract thread name if it exists (for group spaces)
        thread_name = None
        if 'thread' in payload['message']:
            thread_name = payload['message']['thread'].get('name')
        
        # 1. Normalize Text
        clean_text = normalize_text(raw_text)
        if not clean_text:
            return {}

        # 2. Generate Context-Aware Key
        external_key = generate_deterministic_key(space_name, user_name, space_type, thread_name)

        # 3. Async Processing
        async def process_and_reply():
            try:
                # If it's a group chat, we might want the AI to know WHO is speaking in the shared context
                ai_prompt = clean_text
                if space_type != "DIRECT_MESSAGE":
                    ai_prompt = f"[{user_display} says]: {clean_text}"

                # A. Get Context
                raia_id = await get_active_raia_conversation(external_key, user_display)
                
                # B. Get AI Reply
                agent_reply = await send_message_to_raia(raia_id, ai_prompt)
                
                # C. Reply to Google Chat
                # If a thread exists, we must reply to that specific thread
                reply_body = {'text': agent_reply}
                if thread_name:
                    reply_body['thread'] = {'name': thread_name}
                
                chat_service.spaces().messages().create(
                    parent=space_name,
                    body=reply_body,
                    # messageReplyOption must be set to REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD for threads
                    messageReplyOption="REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD" if thread_name else None
                ).execute()
                
            except Exception as e:
                logger.error(f"Pipeline Error: {e}")

        # Execute async
        await process_and_reply()

    # Always acknowledge receipt immediately
    return {}
import os
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI() # Create FastAPI instance

@app.get("/") # Google Chat uses this endpoint for health checks
def check_health(): # Simple check to see if the server is running
    return {"status": "alive", "version": "0.0.1"}

@app.post("/") # Google Chat sends events to this endpoint
# Listens on Root path, can change later

async def handle_chat_event(request: Request):
    # Handles events from Google Chat.
    payload = await request.json() # Waits for JSON payload
    
    # Log the event type for debugging
    print(f"Received event: {payload.get('type')}")
    
    # 1. Handle DM or Mention
    if payload.get("type") == "MESSAGE":
        return {
            "text": "Hey! It's Adam Bot (v0.0.1). I'm here to help!"
        }
    
    # 2. Handle Added to Space
    if payload.get("type") == "ADDED_TO_SPACE":
        return {
            "text": "Thanks for adding me! I am ready to help!"
        }
    ''' 3. Add more event types
    if payload.get("type") == "OTHER_EVENT_TYPE":
        return {
            "text": "Response for other event type"
        }
    '''

    return {}
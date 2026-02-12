import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/")
def check_health():
    return {"status": "alive", "version": "0.0.2"}

@app.post("/")
async def receive_chat_event(request: Request):
    try:
        event = await request.json()
        print(f"FULL EVENT RECEIVED: {event}")
    except Exception as e:
        print(f"JSON Parse Error: {e}")
        return JSONResponse(content={"error": "invalid json"}, status_code=400)

    
    # 1. Check for the new "Interaction Event" format (What you are getting)
    if 'chat' in event and 'messagePayload' in event['chat']:
        user_message = event['chat']['messagePayload']['message']['text']
        user_name = event['chat']['messagePayload']['message']['sender']['displayName']
        
        print(f"Interaction Event Detected. User: {user_name}, Message: {user_message}")
        
        # Google Chat Interaction events expect a specific response format
        return {
            "action": {
                "actionMethod": "NEW_MESSAGE",
            },
            "text": f"I heard you, {user_name}! You said: {user_message}"
        }

    # 2. Check for the legacy "Event" format (What we had before)
    event_type = event.get('type')
    
    if event_type == 'MESSAGE':
        user_message = event.get('message', {}).get('text', '')
        return {"text": f"Legacy match! You said: {user_message}"}

    if event_type == 'ADDED_TO_SPACE':
        return {"text": "Thanks for adding me!"}

    # 3. Fallback
    print(f"Unknown event structure: {event.keys()}")
    return JSONResponse(content={}, status_code=200)
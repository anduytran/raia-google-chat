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

    # 1. Check for the new "Interaction Event" format
    if 'chat' in event and 'messagePayload' in event['chat']:
        payload = event['chat']['messagePayload']
        user_message = payload['message']['text']
        user_name = payload['message']['sender']['displayName']
        
        # EXTRACT THREAD NAME (Crucial for History Off)
        thread_name = payload['message']['thread']['name']
        
        print(f"Interaction Event Detected. User: {user_name}, Message: {user_message}")
        
        # FIX: Use JSONResponse and include the thread
        return JSONResponse(content={
            "text": f"I heard you, {user_name}! You said: {user_message}",
            "thread": {
                "name": thread_name
            }
        })

    # 2. Check for the legacy "Event" format
    event_type = event.get('type')
    
    if event_type == 'MESSAGE':
        user_message = event.get('message', {}).get('text', '')
        # Try to get thread if available, otherwise ignore
        thread_name = event.get('message', {}).get('thread', {}).get('name')
        
        response_data = {"text": f"Legacy match! You said: {user_message}"}
        if thread_name:
            response_data['thread'] = {'name': thread_name}
            
        return JSONResponse(content=response_data)

    if event_type == 'ADDED_TO_SPACE':
        return JSONResponse(content={"text": "Thanks for adding me!"})

    # 3. Fallback
    print(f"Unknown event structure: {event.keys()}")
    return JSONResponse(content={}, status_code=200)
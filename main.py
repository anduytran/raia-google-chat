import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI() # Create FastAPI instance

@app.get("/") # Google Chat uses this endpoint for health checks
def check_health(): # Simple check to see if the server is running
    return {"status": "alive", "version": "0.0.1"}

@app.post("/")
async def receive_chat_event(request: Request):
    # 1. Get the data from the request
    try:
        event = await request.json()
    except Exception as e:
        print(f"Failed to parse JSON from request: {e}")
        return JSONResponse(content={"error": "invalid json"}, status_code=400)

    # 2. PRINT IT TO LOGS (Crucial Step)
    print(f"FULL EVENT RECEIVED: {event}")

    # 3. Check the type
    event_type = event.get("type")
    print(f"Event Type Detected: {event_type}")

    # 4. Handle 'MESSAGE'
    if event_type == "MESSAGE":
        user_message = event.get("message", {}).get("text", "")
        print(f"User said: {user_message}")

        return {"text": f"I heard you! You said: {user_message}"}

    # 5. Handle 'ADDED_TO_SPACE'
    if event_type == "ADDED_TO_SPACE":
        return {"text": "Thanks for adding me! I am ready."}

    # 6. Fallback
    print(f"Unknown event type: {event_type}")
    return JSONResponse(content={}, status_code=200)
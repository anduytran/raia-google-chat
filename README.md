# raia Google Chat (Spaces) Integration

## Project Overview
This project builds a Google Chat App that allows users to have real conversations with a raia AI Agent via Direct Messages (DMs) and Google Chat Spaces. It functions as an intelligent teammate inside Google Workspace.

The system is designed as a lightweight, stateless relay integration. It forwards messages from Google Chat to the raia API and returns the agent's responses back into Google Chat. The integration relies entirely on raia for conversation history and context.

## MVP Scope
This release represents the Minimum Viable Product (MVP).

### Core Features
* **Direct Message Support:** Users can chat 1:1 with the agent; context is maintained.
* **Spaces (Thread) Support:** Users can mention the agent in Spaces; replies are threaded to keep conversations organized.
* **Stateless Architecture:** The relay service stores no local conversation data.
* **Memory Management:** raia acts as the system of record for all conversation state.

## System Architecture
The data flow is linear and stateless:

**Google Chat → Relay Service → raia API → Relay Service → Google Chat**

### Conversation Identity Strategy
To maintain context across different modes (DMs vs. Threads), Google Chat contexts are mapped to raia conversation keys deterministically using the following logic:

* **Direct Messages (DMs):** `gchat:dm:{space.name}`
* **Spaces (Threads):** `gchat:space:{space.name}:{thread.name}`

These keys are passed to raia as `external_identifiers` to upsert or retrieve the specific conversation history.

## Configuration

### 1. Environment Variables
Create a `.env` file in your root directory.

```bash
# Service Configuration
PORT=8080

# raia API Configuration
RAIA_API_KEY=your_raia_api_key
RAIA_AGENT_ID=your_agent_id
RAIA_API_URL=[https://api.raia.co](https://api.raia.co)

# Google Configuration
# (Optional) Project number for request verification
GOOGLE_PROJECT_NUMBER=1234567890
```

### 2. Google Cloud Console Setup

1. Create a Google Cloud Project.
2. Enable the **Google Chat API**.
3. Navigate to the **Configuration** tab in the Chat API settings.
4. **App Name:** raia-bot (or your preferred name).
5. **Avatar URL:** (Optional) URL to your agent's logo.
6. **Connection Settings:** Select "HTTP endpoint" and enter your service URL.
7. **Visibility:** Check "Receive 1:1 messages" and "Join spaces and group conversations".

## Installation

1. **Clone the repository**
```bash
git clone [https://github.com/your-org/raia-google-chat.git](https://github.com/your-org/raia-google-chat.git)
cd raia-google-chat

```


2. **Install dependencies**
```bash
pip install -r requirements.txt

```


3. **Run the application**
```bash
python main.py

```



## Usage Guide

### Direct Messages

1. Open Google Chat.
2. Search for the App and start a chat.
3. Send a message (e.g., "Summarize the project status"). The agent will reply in the DM.

### Spaces (Group Conversations)

1. Add the App to a Space.
2. Mention the App in a message to trigger a response:
`@raia-bot What are the next steps?`
3. The agent will reply inside that specific thread. Subsequent replies in that thread (if mentioned) will maintain the thread's specific context.

## Technical Implementation Details

### Event Handling

The relay service listens for specific Google Chat events:

* **MESSAGE:** Processes text, strips mentions, identifies the source (DM vs Space), and forwards to raia.
* **ADDED_TO_SPACE:** Acknowledges when the bot joins a new context.

### raia API Contract

The interaction with the raia API follows this sequence:

1. **Upsert Conversation:** Uses the deterministic `external_key` + `agent_id`.
2. **Attach Metadata:** Passes Google Chat metadata (space name, user name).
3. **Append Message:** Sends the user's input.
4. **Execute Run:** Triggers the agent to generate a response.
5. **Return Response:** Formats the assistant's output for Google Chat.

### Security

* **Authentication:** Verifies Google OIDC tokens/headers to ensure requests originate from Google.
* **Data Privacy:** No message content is logged to the console/system logs.
* **Secrets:** All API keys and credentials are stored in environment variables.

## Future Roadmap

* **Slash Commands:** Implementation of commands like `/help` or `/reset` to clear context.
* **Rich Cards:** Using Google Chat Cards for formatted responses (tables, images, buttons).
* **File Handling:** Support for analyzing files uploaded to the chat.

## License

This project is licensed under the MIT License.

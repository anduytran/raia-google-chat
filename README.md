Here is the updated README, tailored to exactly match the logic, architecture, and configuration of your provided Python FastAPI code.

# Raia Google Chat (Spaces) Integration

## Project Overview

This project builds a Google Chat App that allows users to have real conversations with a Raia AI Agent via Direct Messages (DMs) and Google Chat Spaces. It functions as an intelligent teammate inside Google Workspace.

The system is designed as a lightweight, stateless relay integration. It forwards messages from Google Chat to the Raia API and returns the agent's responses back into Google Chat. The integration relies entirely on Raia for conversation history and context.

### Core Features

* **Direct Message Support:** Users can chat 1:1 with the agent; context is maintained.
* **Spaces (Thread) Support:** Users can mention the agent in Spaces; replies are threaded to keep conversations organized.
* **Stateless Architecture:** The relay service stores no local conversation data in memory or local databases.
* **Memory Management:** Raia acts as the system of record for all conversation state.

## System Architecture

The data flow is linear and stateless. The FastAPI service running on Google Cloud Run acts as a bridge between the two platforms.

**Google Chat → Relay Service (FastAPI) → Raia API → Relay Service → Google Chat**

### Conversation Identity Strategy

To maintain context across different modes (DMs vs. Threads), Google Chat contexts are mapped to Raia user and conversation keys using a deterministic SHA-256 hash. This ensures the same chat context always routes to the correct Raia memory bank:

* **Direct Messages (DMs):** Tied to the specific user `hash(space.name + user.name)`
* **Spaces (Threads):** Tied to the specific thread so multiple users share the same AI context `hash(thread.name)` (falls back to `space.name` if no thread exists).

These hashed keys are passed to Raia as the `fkId` to search for existing users, resume conversation histories, or create new generic conversations.

## Configuration

### 1. Environment Variables

Create a `.env` file in your root directory (or set these directly in your Google Cloud Run Variables tab).

```bash
# Raia API Configuration
RAIA_API_KEY=your_raia_agent_secret_key
GCP_SA_KEY=your_gcp_service_account_key

```

### 2. Google Cloud Console Setup

1. Create a Google Cloud Project and enable the **Google Chat API**.
2. Navigate to the **Configuration** tab in the Chat API settings.
3. **App Name:** Adam Bot (or your preferred name).
4. **Avatar URL:** (Optional) URL to your agent's logo.
5. **Connection Settings:** Select "HTTP endpoint" and enter your Cloud Run service URL.
6. **Authentication:** Ensure a Service Account is selected so the bot has permission to reply asynchronously.
7. **Visibility:** Check "Receive 1:1 messages" and "Join spaces and group conversations".

## Installation

1. **Clone the repository**

```bash
git clone https://github.com/your-org/raia-google-chat.git
cd raia-google-chat

```

2. **Install dependencies**

```bash
pip install -r requirements.txt

```

3. **Deploy with Docker**
Set up yml file to run deploy tests on branch pushes/pull_requests

## Usage Guide

### Direct Messages

1. Open Google Chat.
2. Search for the App and start a chat.
3. Send a message (e.g., "Summarize the project status"). The agent will reply in the DM, retaining context of previous messages in that DM.

### Spaces (Group Conversations)

1. Add the App to a Space.
2. Mention the App in a message to trigger a response:
`@Adam Bot What are the next steps?`
3. The agent will reply inside that specific thread. Subsequent replies in that thread (if mentioned) will maintain the thread's specific context. The agent is also fed the display name of the user speaking so it can differentiate between team members.

## Technical Implementation Details

### Event Handling

The relay service listens for HTTP POST requests from Google Chat:

* **MESSAGE:** Processes text, strips the `<users/123...>` bot mention tags, identifies the source (DM vs Space), and initiates the async processing pipeline.
* **Fire-and-Forget Logic:** The API instantly returns an empty `200 OK` JSON response to Google Chat to prevent webhook timeouts, while handling the Raia API calls and Google Chat API replies asynchronously.

### Raia API Contract

The interaction with the Raia API follows this sequence:

1. **Search User & History:** Calls `GET /users/search?fkId={key}` to find existing users and their `conversationIds` array.
2. **Upsert User/Conversation:** If no user/history exists, it calls `POST /users` followed by `POST /conversations` to initialize the context.
3. **Append Message:** Sends the user's cleaned text to `POST /conversations/{id}/messages`.
4. **Return Response:** Uses the Python Google API Client (`chat_service.spaces().messages().create`) to push the generated text back to the correct Google Chat space/thread.

### Security

* **Authentication:** Uses Google Application Default Credentials (`google.auth.default()`) automatically provided by Cloud Run to securely authenticate API calls back to Google Chat.
* **Data Privacy:** Raia API keys are handled securely via environment variables.

## Future Roadmap

* **Slash Commands:** Implementation of commands like `/reset` to clear context and force the generation of a new Raia conversation ID.
* **Rich Cards:** Using Google Chat Cards for formatted responses (tables, images, buttons).
* **File Handling:** Support for analyzing files or images uploaded to the chat.

## License

This project is licensed under the MIT License.

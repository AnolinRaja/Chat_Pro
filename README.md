# ChatPRO Backend

ChatPRO is a WhatsApp-like chat backend built with FastAPI, MongoDB, JWT authentication, REST APIs, and WebSockets.

## Current capabilities

- User registration, login, and authenticated user lookup
- JWT bearer authentication with validated signing-secret configuration
- One-to-one conversation creation and listing
- Participant authorization for conversations and messages
- Duplicate conversation prevention using a canonical participant key
- Message creation and chronological retrieval
- Bounded cursor pagination for message history
- Real-time WebSocket messaging with acknowledgements
- Concurrent broadcasting with failed-client isolation
- Connection health metadata and stale-connection cleanup
- MongoDB index creation and definition verification

## Technology stack

- Python
- FastAPI and Uvicorn
- MongoDB with PyMongo
- PyJWT
- bcrypt
- Pydantic
- WebSockets
- Pytest

## Architecture

```text
Client
  |-- REST API ------> FastAPI routes
  |                      |-- authentication
  |                      |-- conversations
  |                      |-- messages
  |                      `-- MongoDB services
  `-- WebSocket -----> FastAPI WebSocket route
                         |-- JWT authentication and conversation authorization
                         |-- ConnectionManager
                         |-- message persistence
                         `-- MongoDB
```

The application entry point is `backend/app/main.py`. Routes delegate persistence and authorization work to services. `ConnectionManager` stores active WebSocket connections in memory for the running process.

## Configuration

Copy `backend/.env.example` to `backend/.env` and replace the placeholders. Do not commit `.env` or real credentials.

| Variable | Purpose | Default |
| --- | --- | --- |
| `APP_NAME` | FastAPI application name | `chatpro-backend` |
| `APP_VERSION` | Application version | `0.1.0` |
| `HOST` | Bind host | `127.0.0.1` |
| `PORT` | Bind port | `8000` |
| `DEBUG` | Debug flag | `false` |
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGODB_DB` | MongoDB database name | `chatpro` |
| `JWT_SECRET_KEY` | JWT signing secret; provide a unique value of at least 32 characters | required |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime | `30` |
| `WEBSOCKET_IDLE_THRESHOLD_SECONDS` | Idle classification threshold, from 1 to 86400 seconds | `300` |

MongoDB must be running and reachable. Index initialization is attempted during application import; failures are logged and verified without causing startup to fail solely because an index is unavailable.

When MongoDB is unavailable, the application remains alive but reports itself as not ready for database-backed requests. The `GET /health` endpoint is a liveness check; `GET /ready` is the database/index readiness gate.

Current in-memory rate limiting and active WebSocket tracking are process-local. In a multi-instance deployment, additional distributed infrastructure is required to keep rate limits and live connection state consistent across nodes.

## Local setup

From the repository root:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

On Linux or macOS, activate the environment with:

```bash
source .venv/bin/activate
```

Edit `.env` with a reachable MongoDB URI and a unique JWT secret of at least 32 characters. Start MongoDB, then run the API:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Container deployment

Build the production-oriented backend image from the repository root:

```bash
docker build -f backend/Dockerfile -t chatpro-backend backend
```

Run one application process and one Uvicorn worker. Supply `MONGODB_URI`, `MONGODB_DB`, and `JWT_SECRET_KEY` at runtime through secure environment configuration; secrets are excluded from the image.

```bash
docker run --rm -p 8000:8000 \
  -e MONGODB_URI="mongodb://host.docker.internal:27017" \
  -e MONGODB_DB="chatpro" \
  -e JWT_SECRET_KEY="replace-with-a-secret-of-at-least-32-characters" \
  chatpro-backend
```

The backend uses an external MongoDB service that runs outside the application container. Production MongoDB deployments should use authentication, TLS, restricted network access, and secure credential injection. Use `/health` for container liveness and `/ready` for traffic readiness; `/ready` is not ready while MongoDB is unavailable or required indexes are invalid.

The one-process limit is required because WebSocket connection state and rate-limit state are process-local. Horizontal scaling and multiple workers are deferred until distributed coordination is designed.

## API documentation

FastAPI provides interactive OpenAPI documentation at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

The host and port should match the values configured in `.env`.

## REST API

### Authentication

`POST /auth/register`

```json
{
  "name": "Anolin Raja",
  "email": "anolin@example.com",
  "password": "StrongPassword123"
}
```

`POST /auth/login` accepts `email` and `password` and returns an access token:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Send the token on protected REST requests with:

```text
Authorization: Bearer <jwt>
```

`GET /auth/me` returns the authenticated user's public identity.

### Conversations

- `POST /conversations` creates or returns the existing one-to-one conversation for the requested participant.
- `GET /conversations` lists conversations for the authenticated user, ordered by `updated_at` descending.

Conversation responses contain `id`, `participants`, `created_at`, and `updated_at`. Only participants can access a conversation.

### Messages

- `POST /conversations/{conversation_id}/messages` creates a message.
- `GET /conversations/{conversation_id}/messages` retrieves messages for an authorized participant.

Message retrieval uses:

- `limit`: optional integer from 1 to 100; default 50
- `cursor`: optional continuation cursor from the previous response

Results are chronological and use `created_at` plus `_id` for deterministic ordering. When another page exists, the endpoint returns the cursor in the `X-Next-Cursor` response header. The response body remains a list of message objects with `id`, `conversation_id`, `sender_id`, `content`, and `created_at`.

### Health and readiness

`GET /health` is a liveness check. It confirms that the FastAPI process is running and reports MongoDB connectivity status without making a readiness decision for database-dependent traffic.

`GET /ready` is a readiness check. It returns HTTP 200 only when MongoDB is reachable and the required MongoDB indexes are present and correctly configured. If MongoDB is unavailable or the required indexes are missing or misconfigured, it returns HTTP 503 with a safe payload that does not expose credentials, secrets, or connection details.

This distinction lets operational checks distinguish between a process that is alive and one that is actually ready to serve database-backed requests.

The application also closes its initialized MongoDB client during FastAPI shutdown. Shutdown is safe when no client exists and client-close errors are logged without exposing sensitive details.

### Request diagnostics

Every HTTP response includes an `X-Request-ID` header generated by the server. The ID is a UUID that helps correlate the request with the corresponding operational log line. Request timing logs record the HTTP method, request path, response status, duration in milliseconds, and the request ID. Sensitive values such as Authorization headers, password fields, JWTs, and message contents are intentionally omitted from logs.

This helps operators trace a failing request without introducing a heavier metrics or tracing stack.

## WebSocket API

Connect to:

```text
ws://127.0.0.1:8000/ws/conversations/{conversation_id}?token=<jwt>
```

The token may also be supplied as a Bearer authorization header when the client supports WebSocket headers. The token is authenticated and the user must be a participant before the connection is accepted.

Send a message as JSON:

```json
{
  "content": "Hello!"
}
```

The sender receives a persisted acknowledgement:

```json
{
  "type": "message_ack",
  "data": {
    "id": "...",
    "conversation_id": "...",
    "sender_id": "...",
    "content": "Hello!",
    "created_at": "..."
  }
}
```

Connected participants receive the broadcast event:

```json
{
  "type": "message",
  "data": {
    "id": "...",
    "conversation_id": "...",
    "sender_id": "...",
    "content": "Hello!",
    "created_at": "..."
  }
}
```

Invalid input or message failures use:

```json
{
  "type": "error",
  "data": {
    "detail": "..."
  }
}
```

Connections are tracked per conversation. Disconnects and failed broadcast clients are cleaned up without blocking healthy clients. Idle connections are classified for health monitoring; they are not automatically closed.

## Database

The backend uses the `users`, `conversations`, and `messages` collections. Important indexes include:

- Unique normalized user email
- Conversation participants
- Sparse unique `participant_key`
- Message conversation ID
- Message conversation and creation-time ordering
- Message conversation, creation-time, and `_id` pagination ordering

The application verifies index names, ordered key definitions, and expected `unique`/`sparse` options. It does not automatically rewrite existing documents or repair conflicting indexes.

## Testing

Run the complete backend suite from `backend`:

```bash
pytest -q
```

The tests cover authentication, authorization, conversations, messages, activity-update retry behavior, pagination and cursors, WebSocket messaging and broadcasting, ConnectionManager behavior, configuration validation, and MongoDB index creation/verification.

For a clean setup check, use a fresh virtual environment and run:

```bash
python -m pip install -r requirements.txt
python -c "import app.main; print('application import succeeded')"
pytest -q
```

## Security notes

- Use a unique JWT secret of at least 32 characters outside local development.
- Keep `.env` out of version control.
- Use HTTPS and WSS behind a production reverse proxy.
- Restrict MongoDB network access and credentials in deployment.
- Do not place tokens, passwords, message content, or database credentials in logs.
- Authentication requests are limited per process and client address using `AUTH_RATE_LIMIT_REQUESTS` within `AUTH_RATE_LIMIT_WINDOW_SECONDS`.
- Rate-limit state is process-local and resets when the process restarts; multi-instance deployment requires a shared rate-limit store.
- WebSocket connections are limited to `WEBSOCKET_MAX_CONNECTIONS_PER_USER` per user, and incoming message size and rate are bounded by the corresponding `WEBSOCKET_*` settings.
 
 

# ChatPRO Frontend

React and Vite frontend foundation for the ChatPRO FastAPI backend.

## Local development

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

The API base URL is configured with `VITE_API_BASE_URL` and defaults to `http://localhost:8000`.

## Available routes

- `/` redirects to `/login`
- `/login` placeholder sign-in page
- `/register` placeholder registration page
- `/chat` placeholder chat page

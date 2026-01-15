# Backend Setup Documentation

## Overview

Simple FastAPI backend that receives user prompt data from the frontend. The backend is set up to receive data and is ready for you to add your ML processing logic.

## Project Structure

```
backend/
  app/
    main.py          # FastAPI application with API endpoints
    services/        # Your ML services (existing)
    ...
  requirements.txt   # Python dependencies
```

## Setup

1. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Run the backend server:
```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

### POST /api/verses/search

Receives user prompt data from the frontend.

**Request Body:**
```json
{
  "mainPrompt": "string - user's input text"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Data received successfully",
  "received_data": {
    "mainPrompt": "user's input text",
    "prompt_length": 123
  }
}
```

**Current Implementation:**
- Receives the `mainPrompt` string in `request.mainPrompt`
- Returns a simple acknowledgment response
- Ready for you to add ML processing logic

## Data Flow

1. Frontend sends POST request to `/api/verses/search` with `{ mainPrompt: "user text" }`
2. Backend receives data in `request.mainPrompt`
3. Add your ML processing in the `search_verses` function
4. Return processed results (verses, embeddings, etc.)

## Frontend Configuration

The frontend is configured to call the backend at:
- Development: `http://localhost:8000/api` (set via `VITE_API_URL` environment variable)
- Default: `http://localhost:5000/api` (if env var not set)

To change the backend URL, create a `.env` file in the project root:
```
VITE_API_URL=http://localhost:8000/api
```

## Next Steps

1. Add your ML processing logic in `app/main.py` in the `search_verses` function
2. Import and use your existing services from `app/services/`
3. Return the processed verse data in the response
4. Update the response model in `PromptResponse` to match your output structure

## CORS Configuration

CORS is configured to allow requests from:
- `http://localhost:5173` (Vite default)
- `http://localhost:3000` (alternative React port)

If you need to add more origins, update the `allow_origins` list in `app/main.py`.

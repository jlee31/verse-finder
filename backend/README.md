# Backend API

Simple FastAPI backend for receiving and processing user prompts.

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the server:
```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Main Endpoint

**POST /api/verses/search**

Receives user prompt data. The `mainPrompt` field contains the user's input text.

Request:
```json
{
  "mainPrompt": "I'm feeling anxious about my future"
}
```

Response (current):
```json
{
  "success": true,
  "message": "Data received successfully",
  "received_data": {
    "mainPrompt": "I'm feeling anxious about my future",
    "prompt_length": 35
  }
}
```

## Adding ML Processing

Edit `app/main.py` in the `search_verses` function. The user's prompt is available as `request.mainPrompt`.

Import your ML services from `app/services/` and process the data. Return the results in the response.

"""
Simple FastAPI backend for verse finder
Receives user prompts and returns data for ML processing
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Verse Finder API")

# CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PromptRequest(BaseModel):
    """Request model for user prompt"""
    mainPrompt: str


class PromptResponse(BaseModel):
    """Response model - placeholder for now"""
    success: bool
    message: str
    received_data: dict


@app.get("/")
def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Verse Finder API is running"}


@app.post("/api/verses/search", response_model=PromptResponse)
async def search_verses(request: PromptRequest):
    """
    Receives user prompt data
    
    Request body:
    {
        "mainPrompt": "string - user's input text"
    }
    
    Returns the received data for now - you can add your ML processing here
    """
    # Data is available in request.mainPrompt
    # Add your ML processing logic here
    
    return PromptResponse(
        success=True,
        message="Data received successfully",
        received_data={
            "mainPrompt": request.mainPrompt,
            "prompt_length": len(request.mainPrompt)
        }
    )

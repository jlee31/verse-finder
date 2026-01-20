from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ml.main import get_quote

app = FastAPI(title="Verse Finder API")

# CORS middleware : used to allow frontend requests from different ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:3001"],  # Vite ports
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

# recieving user prompt in string format
@app.post("/api/verses/search", response_model=PromptResponse)
async def search_verses(request: PromptRequest):

    print("BACKEND RECEIVED POST REQUEST")
    print(f"User Prompt: {request.mainPrompt}")
    print(f"Prompt Length: {len(request.mainPrompt)} characters")
    print("=" * 60)


    # processing the user prompt using ml utils
    quote = get_quote(request.mainPrompt)
    print(f"Quote: {quote}")

    return PromptResponse(
        success=True,
        message="Data received successfully",
        received_data={
            "mainPrompt": request.mainPrompt,
            "quote": quote,
        }
    )

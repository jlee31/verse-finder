from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.rag.retriever import retrieve
from app.rag.generator import generate_reflection
from app.rag.explain import explain_retrieval

load_dotenv() # get the anthropic api key

app = FastAPI(title="Verse Finder API")

# middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a local MVP; tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PromptRequest(BaseModel): # response from frontend
    mainPrompt: str

class Source(BaseModel): # quotes + the recieved cosine similarity score
    text: str
    author: str
    score: float

class PromptResponse(BaseModel): # response (generated reflection AG and R from quotes
    query: str
    reflection: str
    sources: list[Source]

@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Verse Finder API is running"}

@app.post("/api/verses/search", response_model=PromptResponse)
def search_verses(request: PromptRequest):
    # RAG PIPELINE FOUND HERE
    # 1. Retrieve: find the quotes most similar to what the user wrote.
    sources = retrieve(request.mainPrompt, k=3)

    # 2. Generate: hand those quotes to Claude to write a grounded reflection.
    reflection = generate_reflection(request.mainPrompt, sources)

    return PromptResponse(
        query=request.mainPrompt,
        reflection=reflection,
        sources=sources,
    )

class WordImportance(BaseModel):
    """One query word and how much it pulled toward the matched quote."""
    word: str
    weight: float

class ExplainResponse(BaseModel):
    """LIME's view of why the top quote was retrieved for this query."""
    query: str
    matched_quote: str
    matched_author: str
    score: float
    word_importances: list[WordImportance]

@app.post("/api/verses/explain", response_model=ExplainResponse)
def explain_verses(request: PromptRequest):
    """Explain the retrieval: which query words drove the top match (LIME)."""
    return explain_retrieval(request.mainPrompt)

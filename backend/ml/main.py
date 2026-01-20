import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import json
from pathlib import Path

# Get the directory where this file lives
ML_DIR = Path(__file__).parent

model = SentenceTransformer('all-mpnet-base-v2')

quote_embeddings = np.load(ML_DIR / 'quote_embeddings_mpnet.npy')
with open(ML_DIR / 'quotes_list.json') as f:
    quotes = json.load(f)

def get_quote(user_input):
    input_embedding = model.encode([user_input])
    # Cosine Similarity
    cosine_score = cosine_similarity(input_embedding, quote_embeddings)[0]
    best_idx = int(np.argmax(cosine_score))
    best_score = cosine_score[best_idx]
    best_quote = quotes[best_idx]

    if best_score > 0.4:
        return best_quote
    else:
        return "I don't have a good quote for that"


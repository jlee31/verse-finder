import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import json

# model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
model = SentenceTransformer('all-mpnet-base-v2')

quote_embeddings = np.load('quote_embeddings_mpnet.npy')
with open('quotes_list.json') as f:
    quotes = json.load(f)

while True:
    user_input = str(input("Enter input: (type quit to quit)"))
    if user_input == "quit":
        break

    input_embedding = model.encode([user_input])

    # Cosine Similarity
    cosine_score = cosine_similarity(input_embedding, quote_embeddings)[0]
    best_idx = int(np.argmax(cosine_score))
    best_score = cosine_score[best_idx]
    best_quote = quotes[best_idx]

    if best_score > 0.4:
        print("Best matching quote: ")
        print(best_quote)
        print(f"Similarity score is {cosine_score[best_idx]}")
    else:
        print("I don't have a good quote for that")

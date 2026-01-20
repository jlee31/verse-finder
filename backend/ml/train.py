import numpy as np
from sentence_transformers import SentenceTransformer
import json

model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')

quotes = []
with open('quotes.json') as f:
    d = json.load(f)
    d_len = len(d)
    for quote_index in range(d_len):
        quotes.append(d[quote_index]['text'])

quote_embeddings = model.encode(quotes)

np.save('quote_embeddings_mpnet.npy', quote_embeddings)
with open('quotes_list.json', 'w') as f:
    json.dump(quotes, f)

print(f"Saved {len(quotes)} quote embeddings!")

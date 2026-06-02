"""Explainability for the retrieval step.

SHAP/LIME are built to explain classifiers, so they don't fit the LLM
generator. They *do* fit the retriever: we can ask LIME "which words in the
query made this quote get matched?" LIME masks out query words, re-embeds the
masked versions, and watches how the cosine similarity to the matched quote
moves. Words that drop the similarity most when removed are the ones that
mattered — that's the explanation we return.
"""
import numpy as np
from lime.lime_text import LimeTextExplainer
from sklearn.metrics.pairwise import cosine_similarity

# Reuse the model + data already loaded by the retriever (no second copy).
from app.rag.retriever import _model, retrieve

_explainer = LimeTextExplainer(class_names=["off-topic", "relevant"])


def explain_retrieval(query: str, num_features: int = 6, num_samples: int = 300):
    """Explain why the top-matched quote was retrieved for `query`.

    Returns the matched quote plus a list of (word, weight) pairs: positive
    weight means the word pulled the query *toward* that quote.
    """
    top = retrieve(query, k=1)[0]
    target_embedding = _model.encode([top["text"]])

    def similarity_proba(texts: list[str]) -> np.ndarray:
        # LIME expects a classifier's predict_proba: one row per text, columns
        # summing to 1. We frame similarity as P(relevant) and stack the
        # complement as P(off-topic).
        embeddings = _model.encode(texts)
        sims = cosine_similarity(embeddings, target_embedding).reshape(-1)
        sims = np.clip(sims, 0.0, 1.0)
        return np.column_stack([1.0 - sims, sims])

    explanation = _explainer.explain_instance(
        query,
        similarity_proba,
        num_features=num_features,
        num_samples=num_samples,
        labels=[1],  # explain the "relevant" class
    )

    return {
        "query": query,
        "matched_quote": top["text"],
        "matched_author": top["author"],
        "score": top["score"],
        "word_importances": [
            {"word": word, "weight": weight}
            for word, weight in explanation.as_list(label=1)
        ],
    }

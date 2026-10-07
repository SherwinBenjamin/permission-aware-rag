import hashlib
import math
import re
from collections import Counter
from typing import Protocol

import httpx

from app.config import Settings

TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    """a an and are as at be been but by can do does for from has have how i if in into is it
    its me my no not of on or our should so than that the their them then there these they this
    to us was we were what when where which who why will with would you your""".split()
)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def content_tokens(text: str) -> list[str]:
    tokens = []
    for t in TOKEN.findall(text.lower()):
        if t in STOPWORDS:
            continue
        # Crude plural folding so "engineers" matches "engineer".
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        tokens.append(t)
    return tokens


class HashEmbedder:
    """Offline lexical embedding via feature hashing of unigrams and bigrams.

    Lets the app and tests run without a model; swap in a real model for semantic search.
    """

    def __init__(self, dim: int):
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        tokens = content_tokens(text)
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        vec = [0.0] * self.dim
        for feature, count in Counter(features).items():
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vec))
        # pgvector cannot compute cosine distance for a zero vector.
        if norm == 0:
            vec[0] = 1e-6
            return vec
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class OpenAIEmbedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.embedding_model or "text-embedding-3-small"

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            f"{self.settings.openai_base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={"model": self.model, "input": texts, "dimensions": self.settings.embedding_dim},
            timeout=60,
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]


class OllamaEmbedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.embedding_model or "nomic-embed-text"

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            f"{self.settings.ollama_url}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


class ExtractiveLLM:
    """Offline stand-in for an LLM: returns the context sentences that best match the question."""

    SOURCE = re.compile(r'<source id="(\d+)"[^>]*>\n(.*?)\n</source>', re.S)
    SENTENCE = re.compile(r"(?<=[.!?])\s+")

    def complete(self, system: str, user: str) -> str:
        question = user.rsplit("Question:", 1)[-1]
        wanted = set(content_tokens(question))
        scored: dict[frozenset[str], tuple[int, str, str]] = {}
        for source_id, body in self.SOURCE.findall(user):
            for line in body.splitlines():
                if line.lstrip().startswith(("#", "| ---")):
                    continue
                for sentence in self.SENTENCE.split(line.strip(" -*|")):
                    words = frozenset(content_tokens(sentence))
                    overlap = len(wanted & words)
                    if not overlap or len(sentence.split()) < 4:
                        continue
                    # Chunk overlap cuts sentences; keep only the most complete copy.
                    if any(words <= seen for seen in scored):
                        continue
                    for seen in [s for s in scored if s < words]:
                        del scored[seen]
                    scored[words] = (overlap, sentence, source_id)
        if not scored:
            return "I couldn't find that in the documents you have access to."
        best = sorted(scored.values(), key=lambda item: -item[0])[:2]
        return " ".join(f"{sentence} [{source_id}]" for _, sentence, source_id in best)


class OpenAILLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.llm_model or "gpt-4o-mini"

    def complete(self, system: str, user: str) -> str:
        resp = httpx.post(
            f"{self.settings.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class OllamaLLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.llm_model or "llama3.2"

    def complete(self, system: str, user: str) -> str:
        resp = httpx.post(
            f"{self.settings.ollama_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def make_embedder(settings: Settings) -> Embedder:
    match settings.embedding_provider:
        case "hash":
            return HashEmbedder(settings.embedding_dim)
        case "openai":
            return OpenAIEmbedder(settings)
        case "ollama":
            return OllamaEmbedder(settings)
    raise ValueError(f"unknown embedding provider: {settings.embedding_provider}")


def make_llm(settings: Settings) -> LLM:
    match settings.llm_provider:
        case "extractive":
            return ExtractiveLLM()
        case "openai":
            return OpenAILLM(settings)
        case "ollama":
            return OllamaLLM(settings)
    raise ValueError(f"unknown LLM provider: {settings.llm_provider}")

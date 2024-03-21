import random

import pytest
from openai import OpenAI, AsyncOpenAI

import openai_responses
from openai_responses import EmbeddingsMock

EMBEDDING = [random.uniform(0.01, -0.01) for _ in range(100)]


@openai_responses.mock.embeddings(embedding=EMBEDDING)
def test_create_embeddings(embeddings_mock: EmbeddingsMock):
    client = OpenAI(api_key="fakeKey")
    embeddings = client.embeddings.create(
        model="text-embedding-ada-002",
        input="The food was delicious and the waiter...",
        encoding_format="float",
    )
    assert len(embeddings.data) == 1
    assert embeddings.data[0].embedding == EMBEDDING
    assert embeddings.model == "text-embedding-ada-002"
    assert embeddings_mock.create.route.calls.call_count == 1


@pytest.mark.asyncio
@openai_responses.mock.embeddings(embedding=EMBEDDING)
async def test_async_create_embeddings(embeddings_mock: EmbeddingsMock):
    client = AsyncOpenAI(api_key="fakeKey")
    embeddings = await client.embeddings.create(
        model="text-embedding-ada-002",
        input="The food was delicious and the waiter...",
        encoding_format="float",
    )
    assert len(embeddings.data) == 1
    assert embeddings.data[0].embedding == EMBEDDING
    assert embeddings.model == "text-embedding-ada-002"
    assert embeddings_mock.create.route.calls.call_count == 1

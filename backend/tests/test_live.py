"""Real-Ollama smoke tests. Run with: make test-live (CI skips the `live` mark)."""
import json

import pytest

from app.graph.nodes import CLASSIFY_SYSTEM

pytestmark = pytest.mark.live


async def test_real_model_classifies_duplicate_charge():
    from langchain_ollama import ChatOllama
    from app.config import settings
    from langchain_core.messages import HumanMessage, SystemMessage

    model = ChatOllama(model=settings.chat_model, base_url=settings.ollama_base_url,
                       temperature=0.0, format="json")
    resp = await model.ainvoke([SystemMessage(content=CLASSIFY_SYSTEM),
                                HumanMessage(content="I was charged twice this month.")])
    data = json.loads(resp.content)
    assert data["intent"] in ("refund_request", "billing_inquiry")
    assert 0 <= float(data["confidence"]) <= 1
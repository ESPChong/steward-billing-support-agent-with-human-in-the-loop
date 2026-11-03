class Runtime:
    """Model factories injected into the graph — swap real/fake per environment."""

    def __init__(self, chat_factory, classify_factory, embeddings_factory):
        self._chat = chat_factory
        self._classify = classify_factory
        self._embed = embeddings_factory

    def chat_model(self):
        return self._chat()

    def classify_model(self):
        return self._classify()

    def embeddings(self):
        return self._embed()


def default_runtime() -> Runtime:
    from app.llm import get_chat_model, get_embeddings

    return Runtime(
        chat_factory=lambda: get_chat_model(temperature=0.2),
        classify_factory=lambda: get_chat_model(temperature=0.0, json_mode=True),
        embeddings_factory=get_embeddings,
    )
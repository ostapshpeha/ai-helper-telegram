from beanie import Document


class KnowledgeChunk(Document):
    content: str
    section: str
    source: str
    embedding: list[float]

    class Settings:
        name = "knowledge_chunks"

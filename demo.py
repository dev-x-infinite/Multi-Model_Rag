from ingestion import MultiModalIngestion
from vector_store import VectorStoreManager

ing = MultiModalIngestion()
chunks = ing.ingest_file(r"C:\Users\anura\Downloads\Major_Python_Modules_and_AI_Models.pdf")

store = VectorStoreManager()
store.add_chunks(chunks)
print("Stored:", store.count())

results = store.search("what to use for image generation", k=1)
for r in results:
    print(r["distance"], r["source"], r["content"])
    print() 
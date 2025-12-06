from fastapi import FastAPI

app = FastAPI(title="Media Manager")


@app.get("/health")
def health_check():
    return {"status": "healthy"}

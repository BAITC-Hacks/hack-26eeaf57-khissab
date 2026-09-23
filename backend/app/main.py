from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.loader import load_dataset


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dataset = load_dataset()
    yield


app = FastAPI(title="Career Quest API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

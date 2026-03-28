from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from api.wizard_routes import router as wizard_router

app = FastAPI(title="image2asc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(wizard_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}

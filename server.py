from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("dataset", exist_ok=True)


@app.get("/")
def home():
    return {"status": "ok"}


@app.post("/save")
async def save(file: UploadFile):
    image_id = str(uuid.uuid4())

    path = f"dataset/{image_id}.png"

    with open(path, "wb") as f:
        f.write(await file.read())

    return {"id": image_id}

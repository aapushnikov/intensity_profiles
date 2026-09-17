from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import base64
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = "aapushnikov/intensity_profiles"

@app.get("/")
def home():
    return {"status": "ok"}

@app.post("/save")
async def save(file: UploadFile):
    image_id = str(uuid.uuid4())
    filename = f"dataset/{image_id}.png"

    image_data = await file.read()
    encoded_image = base64.b64encode(image_data).decode("utf-8")

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"

    response = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "message": f"Add drawing {image_id}",
            "content": encoded_image,
        },
    )

    if response.status_code not in [200, 201]:
        return {
            "error": "GitHub upload failed",
            "details": response.text
        }

    return {"id": image_id}

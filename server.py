
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import base64
import requests
import json
import re
from urllib.parse import quote

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


def upload_to_github(filename, content, message):
    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}"
        f"/contents/{quote(filename, safe='/')}"
    )

    response = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "message": message,
            "content": base64.b64encode(content).decode("utf-8"),
        },
        timeout=30
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=500,
            detail="GitHub upload failed"
        )


@app.post("/save")
async def save(
    file: UploadFile,
    emotion: str = Form(...),
    participant_id: str = Form(...),
    age: str = Form(...),
    gender: str = Form(...)
):

    if emotion not in ["F", "A", "S"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid emotion"
        )

    participant_id = re.sub(r"\s+", "-", participant_id.strip())

    if not re.fullmatch(r"[\w-]{2,40}", participant_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid participant ID"
        )

    if not age.strip() or not gender.strip():
        raise HTTPException(
            status_code=400,
            detail="Age and gender are required"
        )

    image_id = str(uuid.uuid4())

    image_filename = (
        f"dataset/{participant_id}_{emotion}_{image_id}.png"
    )

    metadata_filename = (
        f"dataset/{participant_id}_{emotion}_{image_id}.json"
    )

    image_data = await file.read()

    metadata = {
        "participant_id": participant_id,
        "age": age.strip(),
        "gender": gender.strip(),
        "emotion": emotion,
        "drawing_id": image_id
    }

    try:
        upload_to_github(
            image_filename,
            image_data,
            f"Add {emotion} drawing for participant {participant_id}"
        )

        upload_to_github(
            metadata_filename,
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=4
            ).encode("utf-8"),
            f"Add metadata for drawing {image_id}"
        )

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to GitHub"
        )

    return {
        "id": participant_id,
        "emotion": emotion,
        "drawing_id": image_id
    }

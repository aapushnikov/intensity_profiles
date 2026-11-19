
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import base64
import requests
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

GITHUB_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

PARTICIPANTS_FILE = "dataset/participants.txt"


@app.get("/")
def home():
    return {"status": "ok"}


def github_url(filename):
    return (
        f"https://api.github.com/repos/{GITHUB_REPO}"
        f"/contents/{quote(filename, safe='/')}"
    )


def upload_image(filename, content, message):
    response = requests.put(
        github_url(filename),
        headers=GITHUB_HEADERS,
        json={
            "message": message,
            "content": base64.b64encode(content).decode("utf-8"),
        },
        timeout=30
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=502,
            detail="Не удалось сохранить рисунок в GitHub"
        )


def save_participant(participant_id, age, gender):
    response = requests.get(
        github_url(PARTICIPANTS_FILE),
        headers=GITHUB_HEADERS,
        timeout=30
    )

    sha = None
    lines = ["participant_id\tage\tgender"]

    if response.status_code == 200:
        file_data = response.json()
        sha = file_data["sha"]

        old_content = base64.b64decode(
            file_data["content"]
        ).decode("utf-8")

        lines = old_content.splitlines()

        if not lines:
            lines = ["participant_id\tage\tgender"]

    elif response.status_code != 404:
        raise HTTPException(
            status_code=502,
            detail="Не удалось прочитать файл участников в GitHub"
        )

    # Убираем старую строку этого участника, если она уже есть.
    updated_lines = [lines[0]]

    for line in lines[1:]:
        fields = line.split("\t", 2)

        if fields and fields[0] != participant_id:
            updated_lines.append(line)

    # Добавляем актуальные данные участника.
    updated_lines.append(
        f"{participant_id}\t{age}\t{gender}"
    )

    content = ("\n".join(updated_lines) + "\n").encode("utf-8")

    payload = {
        "message": f"Update participant {participant_id}",
        "content": base64.b64encode(content).decode("utf-8"),
    }

    if sha:
        payload["sha"] = sha

    save_response = requests.put(
        github_url(PARTICIPANTS_FILE),
        headers=GITHUB_HEADERS,
        json=payload,
        timeout=30
    )

    if save_response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=502,
            detail="Не удалось обновить файл участников в GitHub"
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

    age = " ".join(age.split())
    gender = " ".join(gender.split())

    if not age or not gender:
        raise HTTPException(
            status_code=400,
            detail="Age and gender are required"
        )

    image_id = str(uuid.uuid4())

    image_filename = (
        f"dataset/{participant_id}_{emotion}_{image_id}.png"
    )

    image_data = await file.read()

    if not image_data:
        raise HTTPException(
            status_code=400,
            detail="Empty image"
        )

    try:
        upload_image(
            image_filename,
            image_data,
            f"Add {emotion} drawing for participant {participant_id}"
        )

        save_participant(
            participant_id,
            age,
            gender
        )

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Не удалось связаться с GitHub"
        )

    return {
        "id": participant_id,
        "emotion": emotion,
        "drawing_id": image_id
    }

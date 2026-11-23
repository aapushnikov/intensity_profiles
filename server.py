
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import uuid
import os
import base64
import requests
import re

from urllib.parse import quote
from io import BytesIO
from openpyxl import Workbook, load_workbook


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

EXCEL_FILE = "dataset/participant.xlsx"


# Главная страница API

@app.get("/")
def home():
    return {"status": "ok"}


# Формирование адреса GitHub API

def github_url(filename):
    return (
        f"https://api.github.com/repos/{GITHUB_REPO}"
        f"/contents/{quote(filename, safe='/')}"
    )


# Загрузка файла в GitHub

def upload_file(filename, content, message, sha=None):

    payload = {
        "message": message,
        "content": base64.b64encode(content).decode("utf-8"),
    }

    if sha:
        payload["sha"] = sha

    response = requests.put(
        github_url(filename),
        headers=GITHUB_HEADERS,
        json=payload,
        timeout=30,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось сохранить файл: {filename}",
        )


# Сохранение рисунка

def upload_image(filename, content, message):
    upload_file(filename, content, message)


# Создание или обновление Excel-файла участника

def save_participant(
    participant_id,
    age,
    gender,
    emotion,
    cause,
    importance,
):

    response = requests.get(
        github_url(EXCEL_FILE),
        headers=GITHUB_HEADERS,
        timeout=30,
    )

    sha = None

    # Если Excel уже существует, скачиваем его
    if response.status_code == 200:

        file_data = response.json()
        sha = file_data["sha"]

        excel_content = base64.b64decode(
            file_data["content"]
        )

        workbook = load_workbook(
            BytesIO(excel_content)
        )

        worksheet = workbook.active

    # Если Excel ещё нет, создаём новую книгу
    elif response.status_code == 404:

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Participants"

    else:

        raise HTTPException(
            status_code=502,
            detail="Не удалось прочитать Excel-файл участников",
        )

    # Названия столбцов
    headers = [
        "participant_id",
        "age",
        "gender",
        "fear_cause",
        "fear_importance",
        "anger_cause",
        "anger_importance",
        "sadness_cause",
        "sadness_importance",
    ]

    # Создаём заголовки, если лист пустой
    if worksheet.max_row == 1 and worksheet.cell(1, 1).value is None:

        for col, header in enumerate(headers, start=1):
            worksheet.cell(1, col).value = header

    # Получаем существующие заголовки
    existing_headers = [
        worksheet.cell(1, col).value
        for col in range(1, worksheet.max_column + 1)
    ]

    # Добавляем недостающие столбцы
    for header in headers:

        if header not in existing_headers:

            existing_headers.append(header)

            worksheet.cell(
                1,
                len(existing_headers)
            ).value = header

    # Определяем номер столбца с кодом участника
    participant_id_col = existing_headers.index("participant_id") + 1

    # Ищем существующую строку участника
    participant_row = None

    for row in range(2, worksheet.max_row + 1):

        saved_id = worksheet.cell(
            row,
            participant_id_col
        ).value

        if saved_id == participant_id:
            participant_row = row
            break

    # Если участника ещё нет, добавляем новую строку
    if participant_row is None:
        participant_row = worksheet.max_row + 1

    # Записываем общую информацию
    worksheet.cell(
        participant_row,
        existing_headers.index("participant_id") + 1
    ).value = participant_id

    worksheet.cell(
        participant_row,
        existing_headers.index("age") + 1
    ).value = age

    worksheet.cell(
        participant_row,
        existing_headers.index("gender") + 1
    ).value = gender

    # Определяем столбцы для конкретной эмоции
    emotion_columns = {
        "F": ("fear_cause", "fear_importance"),
        "A": ("anger_cause", "anger_importance"),
        "S": ("sadness_cause", "sadness_importance"),
    }

    cause_column, importance_column = emotion_columns[emotion]

    # Записываем описание события
    worksheet.cell(
        participant_row,
        existing_headers.index(cause_column) + 1
    ).value = cause

    # Записываем числовую оценку значимости
    worksheet.cell(
        participant_row,
        existing_headers.index(importance_column) + 1
    ).value = importance

    # Сохраняем Excel в памяти
    output = BytesIO()
    workbook.save(output)

    excel_bytes = output.getvalue()

    # Загружаем обновлённый Excel в GitHub
    upload_file(
        EXCEL_FILE,
        excel_bytes,
        f"Update participant {participant_id}",
        sha=sha,
    )


# Получение рисунка и ответов от участника

@app.post("/save")
async def save(
    file: UploadFile,
    emotion: str = Form(...),
    participant_id: str = Form(...),
    age: str = Form(...),
    gender: str = Form(...),
    cause: str = Form(...),
    importance: int = Form(...),
):

    # Проверяем тип эмоции
    if emotion not in ["F", "A", "S"]:

        raise HTTPException(
            status_code=400,
            detail="Invalid emotion",
        )

    # Проверяем код участника
    participant_id = re.sub(
        r"\s+",
        "-",
        participant_id.strip(),
    )

    if not re.fullmatch(r"[\w-]{2,40}", participant_id):

        raise HTTPException(
            status_code=400,
            detail="Invalid participant ID",
        )

    # Проверяем и очищаем данные
    age = " ".join(age.split())
    gender = " ".join(gender.split())
    cause = " ".join(cause.split())

    if not age or not gender:

        raise HTTPException(
            status_code=400,
            detail="Age and gender are required",
        )

    if not cause:

        raise HTTPException(
            status_code=400,
            detail="Cause is required",
        )

    if importance not in [1, 2, 3, 4]:

        raise HTTPException(
            status_code=400,
            detail="Importance must be 1, 2, 3 or 4",
        )

    # Создаём уникальное имя рисунка
    image_id = str(uuid.uuid4())

    image_filename = (
        f"dataset/{participant_id}_{emotion}_{image_id}.png"
    )

    # Читаем изображение
    image_data = await file.read()

    if not image_data:

        raise HTTPException(
            status_code=400,
            detail="Empty image",
        )

    try:

        # Сохраняем рисунок
        upload_image(
            image_filename,
            image_data,
            f"Add {emotion} drawing for participant {participant_id}",
        )

        # Сохраняем или обновляем данные Excel
        save_participant(
            participant_id,
            age,
            gender,
            emotion,
            cause,
            importance,
        )

    except requests.RequestException:

        raise HTTPException(
            status_code=502,
            detail="Не удалось связаться с GitHub",
        )

    return {
        "id": participant_id,
        "emotion": emotion,
        "drawing_id": image_id,
    }


import os
import re
import uuid
import base64

import requests

from io import BytesIO
from urllib.parse import quote

from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from openpyxl import Workbook, load_workbook


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройки GitHub.
# Если токен не задан, приложение всё равно запустится,
# но сохранение данных будет недоступно.

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "aapushnikov/intensity_profiles"

EXCEL_FILE = "dataset/participant.xlsx"

GITHUB_API = "https://api.github.com"

GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
}

if GITHUB_TOKEN:
    GITHUB_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


# Проверка наличия токена перед сохранением

def check_github_token():
    if not GITHUB_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="На сервере не настроена переменная GITHUB_TOKEN",
        )


# Формирование адреса GitHub API

def github_url(filename):
    encoded_filename = quote(filename, safe="/")

    return (
        f"{GITHUB_API}/repos/{GITHUB_REPO}"
        f"/contents/{encoded_filename}"
    )


# Загрузка или обновление файла в GitHub

def upload_file(filename, content, message, sha=None):

    check_github_token()

    payload = {
        "message": message,
        "content": base64.b64encode(content).decode("utf-8"),
    }

    if sha:
        payload["sha"] = sha

    try:
        response = requests.put(
            github_url(filename),
            headers=GITHUB_HEADERS,
            json=payload,
            timeout=30,
        )

    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка соединения с GitHub: {str(error)}",
        )

    if response.status_code not in [200, 201]:

        if response.status_code == 409:
            detail = (
                "Файл был одновременно изменён другим запросом. "
                "Попробуйте сохранить ещё раз."
            )
        else:
            detail = (
                f"GitHub не сохранил файл {filename}. "
                f"Код ответа: {response.status_code}. "
                f"Ответ: {response.text[:500]}"
            )

        raise HTTPException(
            status_code=502,
            detail=detail,
        )


# Чтение существующего Excel-файла из GitHub

def download_excel():

    check_github_token()

    try:
        response = requests.get(
            github_url(EXCEL_FILE),
            headers=GITHUB_HEADERS,
            timeout=30,
        )

    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка соединения с GitHub: {str(error)}",
        )

    if response.status_code == 404:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Participants"

        return workbook, worksheet, None

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                "Не удалось прочитать Excel из GitHub. "
                f"Код ответа: {response.status_code}. "
                f"Ответ: {response.text[:500]}"
            ),
        )

    file_data = response.json()

    if "content" not in file_data or not file_data["content"]:
        raise HTTPException(
            status_code=502,
            detail="GitHub не вернул содержимое Excel-файла",
        )

    excel_content = base64.b64decode(
        file_data["content"]
    )

    workbook = load_workbook(
        BytesIO(excel_content)
    )

    worksheet = workbook.active

    return workbook, worksheet, file_data["sha"]


# Создание или обновление строки участника в Excel

def save_participant(
    participant_id,
    age,
    gender,
    emotion,
    cause,
    importance,
):

    workbook, worksheet, sha = download_excel()

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

    # Если лист пустой, записываем заголовки

    if worksheet.max_row == 1 and worksheet.cell(1, 1).value is None:

        for col, header in enumerate(headers, start=1):
            worksheet.cell(1, col).value = header

    # Считываем существующие заголовки

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

    # Находим строку участника

    participant_id_col = existing_headers.index("participant_id") + 1

    participant_row = None

    for row in range(2, worksheet.max_row + 1):

        saved_id = worksheet.cell(
            row,
            participant_id_col
        ).value

        if saved_id == participant_id:
            participant_row = row
            break

    # Если участника ещё нет, создаём новую строку

    if participant_row is None:
        participant_row = worksheet.max_row + 1

    # Записываем общие данные участника

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

    # Соответствие эмоций столбцам Excel

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

    # Записываем значимость именно числом от 1 до 4

    worksheet.cell(
        participant_row,
        existing_headers.index(importance_column) + 1
    ).value = int(importance)

    # Сохраняем книгу в оперативной памяти

    output = BytesIO()
    workbook.save(output)

    excel_bytes = output.getvalue()

    # Загружаем обновлённую книгу в GitHub

    upload_file(
        EXCEL_FILE,
        excel_bytes,
        f"Update participant {participant_id}",
        sha=sha,
    )


# Проверка работы сервера

@app.get("/")
def home():
    return {"status": "ok"}


# Приём рисунка и ответов участника

@app.post("/save")
async def save(
    file: UploadFile = File(...),
    emotion: str = Form(...),
    participant_id: str = Form(...),
    age: str = Form(...),
    gender: str = Form(...),
    cause: str = Form(...),
    importance: int = Form(...),
):

    check_github_token()

    # Проверяем тип эмоции

    if emotion not in ["F", "A", "S"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid emotion",
        )

    # Проверяем код участника

    participant_id = participant_id.strip()

    if not re.fullmatch(r"[A-Z0-9]{8}", participant_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid participant ID",
        )

    # Очищаем данные

    age = age.strip()
    gender = gender.strip()
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

    # Читаем изображение

    image_data = await file.read()

    if not image_data:
        raise HTTPException(
            status_code=400,
            detail="Empty image",
        )

    # Формируем уникальное имя рисунка

    image_id = str(uuid.uuid4())

    image_filename = (
        f"dataset/{participant_id}_{emotion}_{image_id}.png"
    )

    # Сначала сохраняем рисунок

    upload_file(
        image_filename,
        image_data,
        f"Add {emotion} drawing for participant {participant_id}",
    )

    # Затем обновляем Excel

    save_participant(
        participant_id=participant_id,
        age=age,
        gender=gender,
        emotion=emotion,
        cause=cause,
        importance=importance,
    )

    return {
        "id": participant_id,
        "emotion": emotion,
        "drawing_id": image_id,
    }

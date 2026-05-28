"""
Микросервис для получения данных налогоплательщика по ИНН (cabinet.salyk.kg)
Запуск на Railway: gunicorn app:app
"""

import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

API_URL = "https://cabinet.salyk.kg/TinCheck/GetTaxPayer"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://cabinet.salyk.kg/account/register",
    "Accept": "application/json, text/plain, */*",
}

# Используем постоянную сессию
session = requests.Session()
session.headers.update(HEADERS)

# Прогрев (получаем cookies)
try:
    session.get("https://cabinet.salyk.kg/account/register", timeout=5)
except Exception:
    pass


def fetch_taxpayer(inn: str):
    """Возвращает dict с результатом запроса."""
    result = {
        "inn": inn,
        "name": "",
        "rayon": "",
        "status": "ok",
        "error_message": ""
    }
    try:
        resp = session.get(API_URL, params={"Tin": inn}, timeout=15)

        if resp.status_code == 400:
            result["status"] = "not_found"
            result["error_message"] = "ИНН не найден (400)"
            return result
        if resp.status_code != 200:
            result["status"] = "error"
            result["error_message"] = f"HTTP {resp.status_code}"
            return result

        text = resp.text.strip()
        if not text or text == "null":
            result["status"] = "not_found"
            result["error_message"] = "Пустой ответ"
            return result

        data = resp.json()
        if data is None:
            result["status"] = "not_found"
            result["error_message"] = "Нет данных"
        elif isinstance(data, dict):
            name = data.get("name", "")
            if name:
                result["name"] = name
                result["rayon"] = data.get("rayon", "")
            else:
                result["status"] = "not_found"
                result["error_message"] = "Поле name пустое"
        else:
            result["status"] = "error"
            result["error_message"] = "Неожиданный формат ответа"

    except requests.exceptions.Timeout:
        result["status"] = "error"
        result["error_message"] = "Таймаут запроса"
    except requests.exceptions.ConnectionError:
        result["status"] = "error"
        result["error_message"] = "Нет соединения с API"
    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)[:200]

    return result


@app.route("/get_taxpayer", methods=["GET", "POST"])
def get_taxpayer():
    """Эндпоинт для получения ФИО/названия по ИНН.
       GET: /get_taxpayer?inn=12345678901234
       POST: JSON {"inn": "12345678901234"}
    """
    if request.method == "POST":
        data_json = request.get_json(silent=True)
        if data_json and "inn" in data_json:
            inn = str(data_json["inn"]).strip()
        else:
            inn = request.form.get("inn", "").strip()
    else:  # GET
        inn = request.args.get("inn", "").strip()

    if not inn:
        return jsonify({"error": "Параметр 'inn' обязателен"}), 400

    if not inn.isdigit() or len(inn) < 10:
        return jsonify({"error": "Некорректный ИНН (должен содержать только цифры, минимум 10 знаков)"}), 400

    result = fetch_taxpayer(inn)

    response_data = {
        "inn": result["inn"],
        "name": result["name"],
        "status": result["status"]
    }
    # Если нужен ещё код УГНС (rayon), добавьте параметр ?full=1
    if request.args.get("full") or (request.method == "POST" and request.get_json(silent=True, default={}).get("full")):
        response_data["rayon"] = result["rayon"]
        response_data["error_message"] = result["error_message"]

    return jsonify(response_data)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # Для локального теста (Railway использует gunicorn, этот блок не выполнится)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

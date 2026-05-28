import os
import json
import time
import requests
from flask import Flask, request
from functools import wraps

app = Flask(__name__)

API_URL = "https://cabinet.salyk.kg/TinCheck/GetTaxPayer"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://cabinet.salyk.kg/account/register",
    "Accept": "application/json, text/plain, */*",
}

# Сессия + кэш
session = requests.Session()
session.headers.update(HEADERS)

# Простой кэш в памяти: {inn: (timestamp, result_dict)}
cache = {}
CACHE_TTL = 600  # 10 минут

def cache_get(inn):
    if inn in cache:
        ts, data = cache[inn]
        if time.time() - ts < CACHE_TTL:
            return data
        else:
            del cache[inn]
    return None

def cache_set(inn, data):
    cache[inn] = (time.time(), data)

# Прогрев сессии
try:
    session.get("https://cabinet.salyk.kg/account/register", timeout=5)
except Exception:
    pass


def json_utf8(data, status=200):
    return app.response_class(
        response=json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype='application/json'
    )


def fetch_taxpayer(inn: str):
    # Сначала проверим кэш
    cached = cache_get(inn)
    if cached is not None:
        return cached

    result = {
        "inn": inn,
        "name": "",
        "rayon": "",
        "status": "ok",
        "error_message": ""
    }
    try:
        # Таймаут 10 секунд (чтобы Jira не ждала 30+)
        resp = session.get(API_URL, params={"Tin": inn}, timeout=10)

        if resp.status_code == 400:
            result["status"] = "not_found"
            result["error_message"] = "ИНН не найден (400)"
            cache_set(inn, result)
            return result
        if resp.status_code != 200:
            result["status"] = "error"
            result["error_message"] = f"HTTP {resp.status_code}"
            cache_set(inn, result)
            return result

        text = resp.text.strip()
        if not text or text == "null":
            result["status"] = "not_found"
            result["error_message"] = "Пустой ответ"
            cache_set(inn, result)
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
        result["error_message"] = "Таймаут при запросе к salyk.kg (10 сек)"
    except requests.exceptions.ConnectionError:
        result["status"] = "error"
        result["error_message"] = "Нет соединения с API"
    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)[:200]

    cache_set(inn, result)
    return result


@app.route("/get_taxpayer", methods=["GET", "POST"])
def get_taxpayer():
    if request.method == "POST":
        data_json = request.get_json(silent=True)
        if data_json and "inn" in data_json:
            inn = str(data_json["inn"]).strip()
        else:
            inn = request.form.get("inn", "").strip()
    else:
        inn = request.args.get("inn", "").strip()

    if not inn:
        return json_utf8({"error": "Параметр 'inn' обязателен"}, 400)
    if not inn.isdigit() or len(inn) < 10:
        return json_utf8({"error": "Некорректный ИНН (должен содержать только цифры, минимум 10 знаков)"}, 400)

    result = fetch_taxpayer(inn)

    response_data = {
        "inn": result["inn"],
        "name": result["name"],
        "status": result["status"]
    }

    full = False
    if request.method == "GET":
        full = request.args.get("full") == "1"
    elif request.method == "POST":
        data_json = request.get_json(silent=True)
        if data_json:
            full = data_json.get("full", False)

    if full:
        response_data["rayon"] = result["rayon"]
        response_data["error_message"] = result["error_message"]

    return json_utf8(response_data)


@app.route("/health", methods=["GET"])
def health():
    return json_utf8({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

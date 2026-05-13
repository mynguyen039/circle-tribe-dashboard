import os
import json
import requests
from flask import Flask, request, Response, send_file

app = Flask(__name__)

NOTION_TOKEN  = os.environ.get("NOTION_TOKEN", "")
GEMINI_KEY    = os.environ.get("GEMINI_KEY", "")
NOTION_BASE   = "https://api.notion.com/v1"
GEMINI_URL    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Notion-Version",
}


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/ai", methods=["POST", "OPTIONS"])
def gemini_proxy():
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    try:
        body = request.get_json()
        # Convert Claude-style messages to Gemini format
        messages = body.get("messages", [])
        system = body.get("system", "")
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": system}]})
            contents.append({"role": "model", "parts": [{"text": "OK, understood."}]})
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        
        gemini_body = {"contents": contents, "generationConfig": {"maxOutputTokens": 1000}}
        url = GEMINI_URL + "?key=" + GEMINI_KEY
        res = requests.post(url, json=gemini_body, timeout=60)
        
        # Convert Gemini response to Claude-style format
        data = res.json()
        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        out = {"content": [{"type": "text", "text": text}]}
        return Response(json.dumps(out), status=200,
                        headers={**CORS_HEADERS, "Content-Type": "application/json"})
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=500,
                        headers={**CORS_HEADERS, "Content-Type": "application/json"})


@app.route("/<path:path>", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
def notion_proxy(path):
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    try:
        notion_url = NOTION_BASE + "/" + path
        if request.query_string:
            notion_url += "?" + request.query_string.decode()

        res = requests.request(
            method=request.method,
            url=notion_url,
            headers={
                "Authorization": "Bearer " + NOTION_TOKEN,
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            data=request.get_data(),
            timeout=30,
        )
        return Response(res.content, status=res.status_code,
                        headers={**CORS_HEADERS, "Content-Type": "application/json"})
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=500,
                        headers={**CORS_HEADERS, "Content-Type": "application/json"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8787))
    app.run(host="0.0.0.0", port=port)

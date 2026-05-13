import os
import json
import requests
from flask import Flask, request, Response, send_file

app = Flask(__name__)

NOTION_TOKEN  = os.environ.get("NOTION_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
NOTION_BASE   = "https://api.notion.com/v1"
CLAUDE_URL    = "https://api.anthropic.com/v1/messages"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Notion-Version",
}


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/claude", methods=["POST", "OPTIONS"])
def claude_proxy():
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    try:
        res = requests.post(
            CLAUDE_URL,
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            data=request.get_data(),
            timeout=60,
        )
        return Response(res.content, status=res.status_code,
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

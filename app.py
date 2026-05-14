import os
import json
import requests
from flask import Flask, request, Response, send_file

app = Flask(__name__)

NOTION_TOKEN  = os.environ.get("NOTION_TOKEN", "")
GEMINI_KEY    = os.environ.get("GEMINI_KEY", "")
NOTION_BASE   = "https://api.notion.com/v1"
GEMINI_URL    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Notion-Version",
}


@app.route("/")
def index():
    return send_file("index.html")

@app.route("/api/config")
def api_config():
    # Returns server config so frontend doesn't need manual token input
    return Response(
        json.dumps({"notion_token": NOTION_TOKEN, "has_ai": bool(GEMINI_KEY)}),
        headers={**CORS_HEADERS, "Content-Type": "application/json"}
    )



# CHAT HISTORY ENDPOINTS
CHAT_DB_ID = os.environ.get("CHAT_DB_ID", "")

@app.route("/api/chat/save", methods=["POST", "OPTIONS"])
def save_chat():
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    try:
        body = request.get_json()
        title = body.get("title", "Chat Session")
        messages = body.get("messages", [])
        db_id = body.get("db_id", CHAT_DB_ID)
        if not db_id:
            return Response(json.dumps({"error": "No CHAT_DB_ID"}), status=400,
                            headers={**CORS_HEADERS, "Content-Type": "application/json"})
        children = []
        for msg in messages:
            role_label = "User" if msg.get("role") == "user" else "AI"
            text = str(msg.get("content", ""))[:1900]
            children.append({"object":"block","type":"paragraph",
                "paragraph":{"rich_text":[{"type":"text","text":{"content":role_label+": "+text}}]}})
        page_data = {
            "parent": {"database_id": db_id},
            "properties": {"Name": {"title": [{"text": {"content": title}}]}},
            "children": children
        }
        res = requests.post("https://api.notion.com/v1/pages",
            headers={"Authorization":"Bearer "+NOTION_TOKEN,"Notion-Version":"2022-06-28","Content-Type":"application/json"},
            json=page_data, timeout=30)
        data = res.json()
        return Response(json.dumps({"ok": True, "id": data.get("id","")}),
                        headers={**CORS_HEADERS,"Content-Type":"application/json"})
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=500,
                        headers={**CORS_HEADERS,"Content-Type":"application/json"})

@app.route("/api/chat/list", methods=["GET", "OPTIONS"])
def list_chats():
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    try:
        db_id = request.args.get("db_id", CHAT_DB_ID)
        if not db_id:
            return Response(json.dumps({"results":[]}), headers={**CORS_HEADERS,"Content-Type":"application/json"})
        res = requests.post("https://api.notion.com/v1/databases/"+db_id+"/query",
            headers={"Authorization":"Bearer "+NOTION_TOKEN,"Notion-Version":"2022-06-28","Content-Type":"application/json"},
            json={"sorts":[{"timestamp":"created_time","direction":"descending"}],"page_size":30}, timeout=30)
        data = res.json()
        results = []
        for page in data.get("results",[]):
            t = page.get("properties",{}).get("Name",{})
            title = t.get("title",[{}])[0].get("plain_text","") if t.get("title") else ""
            results.append({"id":page["id"],"title":title,"created":page.get("created_time","")[:10]})
        return Response(json.dumps({"results":results}), headers={**CORS_HEADERS,"Content-Type":"application/json"})
    except Exception as e:
        return Response(json.dumps({"results":[],"error":str(e)}), headers={**CORS_HEADERS,"Content-Type":"application/json"})

@app.route("/api/chat/load/<page_id>", methods=["GET", "OPTIONS"])
def load_chat(page_id):
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    try:
        res = requests.get("https://api.notion.com/v1/blocks/"+page_id+"/children",
            headers={"Authorization":"Bearer "+NOTION_TOKEN,"Notion-Version":"2022-06-28"}, timeout=30)
        data = res.json()
        messages = []
        for block in data.get("results",[]):
            if block.get("type") == "paragraph":
                texts = block["paragraph"].get("rich_text",[])
                text = "".join(t.get("plain_text","") for t in texts)
                if text.startswith("User: "):
                    messages.append({"role":"user","content":text[6:]})
                elif text.startswith("AI: "):
                    messages.append({"role":"assistant","content":text[4:]})
        return Response(json.dumps({"messages":messages}), headers={**CORS_HEADERS,"Content-Type":"application/json"})
    except Exception as e:
        return Response(json.dumps({"messages":[],"error":str(e)}), headers={**CORS_HEADERS,"Content-Type":"application/json"})


@app.route("/api/update_page", methods=["POST", "OPTIONS"])
def update_page():
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    try:
        body = request.get_json()
        page_id = body.get("page_id","").replace("-","")
        props = body.get("properties", {})
        if not page_id:
            return Response(json.dumps({"error":"No page_id"}), status=400,
                            headers={**CORS_HEADERS,"Content-Type":"application/json"})
        res = requests.patch(
            "https://api.notion.com/v1/pages/"+page_id,
            headers={"Authorization":"Bearer "+NOTION_TOKEN,"Notion-Version":"2022-06-28","Content-Type":"application/json"},
            json={"properties": props}, timeout=30)
        data = res.json()
        return Response(json.dumps({"ok": res.status_code==200, "id": data.get("id",""), "error": data.get("message","")}),
                        headers={**CORS_HEADERS,"Content-Type":"application/json"})
    except Exception as e:
        return Response(json.dumps({"error":str(e)}), status=500,
                        headers={**CORS_HEADERS,"Content-Type":"application/json"})


@app.route("/ai", methods=["POST", "OPTIONS"])
def gemini_proxy():
    if request.method == "OPTIONS":
        return Response("", headers=CORS_HEADERS)
    
    if not GEMINI_KEY:
        err = {"content": [{"type": "text", "text": "GEMINI_KEY chua duoc set trong Render Environment Variables"}]}
        return Response(json.dumps(err), status=200, headers={**CORS_HEADERS, "Content-Type": "application/json"})
    
    try:
        body = request.get_json()
        messages = body.get("messages", [])
        system = body.get("system", "")
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": system}]})
            contents.append({"role": "model", "parts": [{"text": "Da hieu. San sang ho tro."}]})
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            text = m.get("content", "")
            if text:
                contents.append({"role": role, "parts": [{"text": text}]})
        
        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Xin chao"}]})

        gemini_body = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.7}
        }

        # Model priority: Gemini 3.1 Flash Lite = best free (500 RPD, smart, fast)
        MODELS = [
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent",
            "https://generativelanguage.googleapis.com/v1beta/models/gemma-3-27b-it:generateContent",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
        ]

        res = None
        data = None
        for model_url in MODELS:
            url = model_url + "?key=" + GEMINI_KEY
            res = requests.post(url, json=gemini_body, timeout=60)
            data = res.json()
            print("Trying model:", model_url.split("models/")[1].split(":")[0], "->", res.status_code)
            if res.status_code == 200:
                break

        if res.status_code != 200:
            print("All models failed:", json.dumps(data)[:300])
            err_msg = data.get("error", {}).get("message", "Gemini API error " + str(res.status_code))
            out = {"content": [{"type": "text", "text": "Loi Gemini: " + err_msg}]}
            return Response(json.dumps(out), status=200, headers={**CORS_HEADERS, "Content-Type": "application/json"})
        
        candidates = data.get("candidates", [])
        if not candidates:
            out = {"content": [{"type": "text", "text": "Gemini khong tra ve ket qua. Kiem tra GEMINI_KEY trong Render."}]}
            return Response(json.dumps(out), status=200, headers={**CORS_HEADERS, "Content-Type": "application/json"})
        
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        out = {"content": [{"type": "text", "text": text}]}
        return Response(json.dumps(out), status=200,
                        headers={**CORS_HEADERS, "Content-Type": "application/json"})
    except Exception as e:
        print("AI proxy exception:", str(e))
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

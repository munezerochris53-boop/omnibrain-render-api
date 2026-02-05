import os, base64, tempfile, subprocess, hashlib
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app)

# =========================
# ENV
# =========================
API_KEYS = [k.strip() for k in os.environ.get("API_KEYS","").split(",") if k.strip()]
APP_TOKEN = os.environ.get("APP_TOKEN","secret")

# =========================
# SECURITY
# =========================
@app.before_request
def secure():
    if request.headers.get("x-app-token") != APP_TOKEN:
        return jsonify({"error":"Unauthorized"}),401

# =========================
# AI CALL
# =========================
def call_one_api(key, messages):
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type":"application/json"
        },
        json={
            "model":"gpt-4o-mini",
            "messages":messages
        },
        timeout=30
    )
    return r.json()["choices"][0]["message"]["content"]

def call_all_parallel(messages):
    results=[]
    with ThreadPoolExecutor(max_workers=10) as exe:
        futures=[exe.submit(call_one_api,k,messages) for k in API_KEYS]
        for f in as_completed(futures):
            try: results.append(f.result())
            except: pass
    return results

# =========================
# CLEAN + SCORE
# =========================
def dedupe(lst):
    seen=set(); out=[]
    for a in lst:
        h=hashlib.md5(a.encode()).hexdigest()
        if h not in seen:
            seen.add(h); out.append(a)
    return out

def score(lst):
    return sorted(lst,key=lambda x:len(x),reverse=True)

def merge_answers(lst):
    if not lst: return "No valid answer"
    prompt="Huja ibisubizo bikurikira ubigire answer imwe nziza:\n\n"
    for i,a in enumerate(lst[:5],1):
        prompt+=f"{i}. {a}\n\n"
    return call_one_api(API_KEYS[0],[{"role":"user","content":prompt}])

# =========================
# TEXT
# =========================
@app.route("/api/text",methods=["POST"])
def text():
    q=request.json.get("prompt","")
    raw=call_all_parallel([{"role":"user","content":q}])
    final=merge_answers(score(dedupe(raw)))
    return jsonify({"answer":final})

# =========================
# IMAGE
# =========================
@app.route("/api/image",methods=["POST"])
def image():
    img=request.files.get("image")
    if not img: return jsonify({"error":"No image"}),400
    img64=base64.b64encode(img.read()).decode()

    raw=call_all_parallel([{
        "role":"user",
        "content":[
            {"type":"text","text":"Describe this image clearly"},
            {"type":"image_url","image_url":f"data:image/jpeg;base64,{img64}"}
        ]
    }])

    final=merge_answers(score(dedupe(raw)))
    return jsonify({"answer":final})

# =========================
# VIDEO (FFMPEG)
# =========================
@app.route("/api/video",methods=["POST"])
def video():
    vid=request.files.get("video")
    if not vid: return jsonify({"error":"No video"}),400

    with tempfile.TemporaryDirectory() as tmp:
        vp=os.path.join(tmp,"v.mp4")
        fp=os.path.join(tmp,"f.jpg")
        vid.save(vp)

        subprocess.run(
            ["ffmpeg","-y","-i",vp,"-vframes","1",fp],
            check=True
        )

        img64=base64.b64encode(open(fp,"rb").read()).decode()

    raw=call_all_parallel([{
        "role":"user",
        "content":[
            {"type":"text","text":"Describe this video"},
            {"type":"image_url","image_url":f"data:image/jpeg;base64,{img64}"}
        ]
    }])

    final=merge_answers(score(dedupe(raw)))
    return jsonify({"answer":final})

# =========================
# START
# =========================
if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)

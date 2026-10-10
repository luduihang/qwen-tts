"""Stability check: repeat each variant x2, alternating, to separate prompt effect from vLLM nondeterminism."""
import base64, json, time
import requests

BASE = "http://192.168.0.190:8001"
MODEL = "Qwen3-ASR-1.7B"
WAV = open("/tmp/spike/sample15.wav", "rb").read()
B64 = base64.b64encode(WAV).decode()
AUDIO_URL = f"data:audio/wav;base64,{B64}"
MINGLEI_SYS = (
    "这是一段命理学（八字、紫微斗数）讲座的音频转写任务。请转写为文字，"
    "输出纯转写文本，不要解释。同音词请优先采用命理学规范术语："
    "八字、四柱、天干、地支、五行、阴阳、日主、大运、流年、喜用神、用神、正财、偏财、"
    "正官、七杀、正印、偏印、食神、伤官、比肩、劫财、纳音、命宫、身宫、桃花、驿马、华盖、空亡、正缘。"
)
RES = "/tmp/spike/results"

def chat(system, name):
    msgs = (["system"] and [{"role": "system", "content": system}] if system else [])
    msgs.append({"role": "user", "content": [{"type": "audio_url", "audio_url": {"url": AUDIO_URL}}]})
    body = {"model": MODEL, "messages": msgs, "temperature": 0, "max_tokens": 256}
    r = requests.post(f"{BASE}/v1/chat/completions", json=body, timeout=120)
    open(f"{RES}/{name}.json", "w").write(r.text)
    return r.status_code, r.json()["choices"][0]["message"]["content"]

def transcribe(extra, name):
    fields = {"model": MODEL}; fields.update(extra)
    r = requests.post(f"{BASE}/v1/audio/transcriptions", data=fields,
                      files={"file": ("sample15.wav", WAV, "audio/wav")}, timeout=120)
    open(f"{RES}/{name}.json", "w").write(r.text)
    return r.status_code, r.json().get("text", "<no text>")

runs = {}
# 2 rounds, alternating order each round
for rnd in (1, 2):
    order = ["t2_baseline", "t2_with_prompt", "t1_no_system", "t1_with_system"] if rnd == 1 else \
            ["t1_with_system", "t2_baseline", "t1_no_system", "t2_with_prompt"]
    for name in order:
        if name == "t2_baseline": code, text = transcribe({}, f"{name}_r{rnd}")
        elif name == "t2_with_prompt": code, text = transcribe({"prompt": MINGLEI_SYS}, f"{name}_r{rnd}")
        elif name == "t1_no_system": code, text = chat(None, f"{name}_r{rnd}")
        else: code, text = chat(MINGLEI_SYS, f"{name}_r{rnd}")
        runs.setdefault(name, []).append((code, text))
        print(f"r{rnd} {name:<20} {code} {text}", flush=True)
        time.sleep(1)

print("\n--- within-variant consistency ---")
for name, lst in runs.items():
    texts = {t for _, t in lst}
    print(f"{name:<20} {'CONSISTENT' if len(texts)==1 else f'{len(texts)} variants'}")

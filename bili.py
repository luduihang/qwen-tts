"""B 站客户端：BV 号 → 标题/时长 + DASH 音频流下载到临时目录。

契约（见 TASKS.md 契约总览）：
    get_audio(bvid, cfg) -> (title, duration_s, local_path)
    失败抛 BiliError(message, code)，code ∈ {invalid_bvid, not_found, fetch_failed}
"""
import re
from pathlib import Path

import requests

#: BV 号格式：BV 前缀 + 10 位（首位非 0）
BV_RE = re.compile(r"^BV[1-9A-Za-z]{10}$")

VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"

#: 需要登录态才可见 / 不存在的常见返回码 → not_found
NOT_FOUND_CODES = {-404, 62002, 40004}

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}


class BiliError(Exception):
    """B 站拉取失败；code ∈ {invalid_bvid, not_found, fetch_failed}。"""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _headers(cfg):
    headers = dict(_BASE_HEADERS)
    cookie = (cfg.get("bilibili") or {}).get("cookie") or ""
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _get_json(url, params, headers, timeout):
    """请求 B 站 JSON 接口；网络/HTTP/业务码异常统一抛 BiliError。"""
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise BiliError(f"B 站接口请求失败 {url}: {e}", "fetch_failed")
    if r.status_code != 200:
        raise BiliError(f"B 站接口 HTTP {r.status_code} {url}", "fetch_failed")
    try:
        data = r.json()
    except ValueError as e:
        raise BiliError(f"B 站接口响应非 JSON: {e}", "fetch_failed")
    code = data.get("code")
    if code != 0:
        err_code = "not_found" if code in NOT_FOUND_CODES else "fetch_failed"
        raise BiliError(
            f"B 站接口错误 code={code} message={data.get('message')!r}", err_code
        )
    return data


def get_audio(bvid, cfg):
    """BV 号 → 音频落盘。

    返回 (title, duration_s, local_path)；local_path = temp_dir/{bvid}.m4a。
    """
    if not isinstance(bvid, str) or not BV_RE.match(bvid):
        raise BiliError(f"非法 BV 号: {bvid!r}", "invalid_bvid")

    headers = _headers(cfg)
    timeout = (cfg.get("timeout") or {}).get("download_s", 300)

    view = _get_json(VIEW_URL, {"bvid": bvid}, headers, timeout)
    vdata = view.get("data") or {}
    title = vdata.get("title") or ""
    duration_s = vdata.get("duration") or 0
    cid = vdata.get("cid")
    if not cid:
        raise BiliError(f"view 响应缺少 cid: {vdata!r}", "fetch_failed")

    play = _get_json(
        PLAYURL_URL, {"bvid": bvid, "cid": cid, "fnval": 16}, headers, timeout
    )
    dash = (play.get("data") or {}).get("dash")
    if not dash or not dash.get("audio"):
        raise BiliError("playurl 未返回 DASH 音频流", "fetch_failed")
    audio_url = dash["audio"][0].get("baseUrl")
    if not audio_url:
        raise BiliError("playurl 音频流缺少 baseUrl", "fetch_failed")

    out_path = Path(cfg["temp_dir"]) / f"{bvid}.m4a"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(
            audio_url, headers=headers, stream=True, timeout=timeout
        ) as r:
            if r.status_code != 200:
                raise BiliError(f"音频流下载 HTTP {r.status_code}", "fetch_failed")
            with out_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if chunk:
                        f.write(chunk)
    except requests.RequestException as e:
        raise BiliError(f"音频流下载失败: {e}", "fetch_failed")

    return title, duration_s, str(out_path)

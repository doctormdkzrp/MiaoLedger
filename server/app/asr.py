"""火山引擎豆包流式识别 2.0（整段送完取最终文本）。

App 端把「按住说话」录成 16k 单声道 wav 传上来，这里整段送给火山，
拿回一句带标点的文字。密钥从环境变量读：VOLC_API_KEY / VOLC_RESOURCE_ID。
"""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import os
import uuid
import wave

import websockets

URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
DEFAULT_RESOURCE = "volc.seedasr.sauc.duration"


def _header(message_type: int = 0x01, flags: int = 0x00, serial: int = 0x01, comp: int = 0x01) -> bytearray:
    h = bytearray()
    h.append((0x01 << 4) | 1)
    h.append((message_type << 4) | flags)
    h.append((serial << 4) | comp)
    h.append(0)
    return h


def _parse(res: bytes) -> dict:
    if len(res) < 4:
        return {}
    if (res[1] >> 4) == 0x0F:  # 错误帧
        return {
            "code": int.from_bytes(res[4:8], "big"),
            "payload_msg": json.loads(res[12:].decode("utf-8", "replace") or "{}"),
        }
    off = 4
    if res[1] & 0x01:
        off += 4
    length = int.from_bytes(res[off:off + 4], "big")
    off += 4
    try:
        return {"payload_msg": json.loads(res[off:off + length].decode("utf-8", "replace"))}
    except Exception as e:  # 不认识的帧，跳过
        return {"error": str(e)}


async def _transcribe(pcm: bytes, rate: int) -> str:
    key = os.environ.get("VOLC_API_KEY", "")
    if not key:
        raise RuntimeError("没配 VOLC_API_KEY")
    headers = {
        "X-Api-Key": key,
        "X-Api-Resource-Id": os.environ.get("VOLC_RESOURCE_ID", DEFAULT_RESOURCE),
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
    last = ""
    async with websockets.connect(
        URL, additional_headers=headers, max_size=100_000_000, ping_interval=None, close_timeout=5
    ) as ws:
        req = {
            "user": {"uid": "miaoledger"},
            "request": {
                "reqid": str(uuid.uuid4()),
                "workflow": "audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate",
                "show_utterances": True,
                "result_type": "single",
                "sequence": 1,
                "end_window_size": 800,
            },
            "audio": {"format": "pcm", "codec": "pcm", "rate": rate, "bits": 16, "channel": 1},
        }
        payload = gzip.compress(json.dumps(req).encode())
        msg = bytearray(_header())
        msg.extend(len(payload).to_bytes(4, "big"))
        msg.extend(payload)
        await ws.send(bytes(msg))
        init = _parse(await ws.recv())
        if init.get("code") not in (None, 1000):
            raise RuntimeError(f"火山返回错误：{init}")

        chunk = max(int(rate * 2 * 0.2), 3200)
        for i in range(0, len(pcm), chunk):
            body = gzip.compress(pcm[i:i + chunk])
            m = bytearray(_header(message_type=0x02))
            m.extend(len(body).to_bytes(4, "big"))
            m.extend(body)
            await ws.send(bytes(m))
            await asyncio.sleep(0.01)
        tail = bytearray(_header(message_type=0x02, flags=0x02))
        body = gzip.compress(b"")
        tail.extend(len(body).to_bytes(4, "big"))
        tail.extend(body)
        await ws.send(bytes(tail))

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
            except (asyncio.TimeoutError, Exception):
                break
            pm = _parse(raw).get("payload_msg") or {}
            res = pm.get("result") or {}
            if res.get("text"):
                last = res["text"]
            seq = pm.get("sequence")
            if isinstance(seq, int) and seq < 0:
                break
    return last.strip()


def transcribe_wav(data: bytes) -> str:
    """data: 整个 wav 文件字节。返回识别文本（可能为空串）。"""
    with wave.open(io.BytesIO(data), "rb") as wf:
        pcm = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
        channels = wf.getnchannels()
    if channels > 1:  # 双声道就取左声道
        pcm = pcm[0::2]
        pcm = pcm[: len(pcm) // 2 * 2]
    if len(pcm) < rate:  # 不到半秒，基本是误触
        return ""
    return asyncio.run(_transcribe(pcm, rate))

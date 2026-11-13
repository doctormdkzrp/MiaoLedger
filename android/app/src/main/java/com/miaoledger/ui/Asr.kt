package com.miaoledger.ui

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import com.miaoledger.data.Api
import java.io.ByteArrayOutputStream

/**
 * 按住说话：麦克风录 16k 单声道 PCM，松手包成 wav 传给服务端，
 * 服务端调火山引擎识别成文字再回来。
 */
class CloudAsr(
    private val ctx: Context,
    private val api: Api,
    private val onState: (String) -> Unit = {},
    private val onFinal: (String) -> Unit = {},
    private val onError: (String) -> Unit = {},
) {
    companion object {
        private const val SR = 16000
        private const val TAG = "CloudAsr"
    }

    private var rec: AudioRecord? = null
    private var worker: Thread? = null
    @Volatile private var recording = false
    private val buf = ByteArrayOutputStream()

    @SuppressLint("MissingPermission")
    fun start() {
        if (recording) return
        val min = AudioRecord.getMinBufferSize(SR, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) {
            onError("麦克风不可用")
            return
        }
        val r = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SR,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            min * 2,
        )
        if (r.state != AudioRecord.STATE_INITIALIZED) {
            runCatching { r.release() }
            onError("麦克风被占用，稍后再试")
            return
        }
        rec = r
        buf.reset()
        recording = true
        val started = runCatching { r.startRecording() }.onFailure { Log.w(TAG, "startRecording failed", it) }.isSuccess
        Log.i(TAG, "start: state=${r.state} started=$started")
        worker = Thread {
            val tmp = ByteArray(min)
            while (recording) {
                val n = runCatching { r.read(tmp, 0, tmp.size) }.getOrDefault(0)
                if (n > 0) buf.write(tmp, 0, n)
            }
            runCatching { r.stop() }
            runCatching { r.release() }
        }.also { it.start() }
        onState("正在听…")
    }

    fun stop() {
        if (!recording) return
        recording = false
        onState("识别中…")
        val t = worker
        Thread {
            runCatching { t?.join(1500) }
            val pcm = buf.toByteArray()
            Log.i(TAG, "stop: pcm=${pcm.size} bytes (~${pcm.size / 32}ms)")
            if (pcm.size < SR / 2) {          // 不到半秒，当误触
                onError("没听清，再说一次")
                return@Thread
            }
            val wav = wrapWav(pcm, SR)
            runCatching { api.asr(wav) }
                .onSuccess { text ->
                    if (text.isBlank()) onError("没听清，再说一次") else onFinal(text)
                }
                .onFailure { e ->
                    Log.w(TAG, "asr failed", e)
                    onError("识别失败：${e.message?.take(60)}")
                }
        }.start()
    }

    fun cancel() {
        recording = false
        runCatching { rec?.stop() }
        runCatching { rec?.release() }
        rec = null
        buf.reset()
    }

    fun destroy() {
        cancel()
        worker = null
    }

    private fun wrapWav(pcm: ByteArray, rate: Int): ByteArray {
        val out = ByteArrayOutputStream()
        val dataLen = pcm.size
        val totalLen = dataLen + 36
        fun le32(v: Int) = byteArrayOf(
            (v and 0xff).toByte(), ((v shr 8) and 0xff).toByte(),
            ((v shr 16) and 0xff).toByte(), ((v shr 24) and 0xff).toByte(),
        )
        fun le16(v: Int) = byteArrayOf((v and 0xff).toByte(), ((v shr 8) and 0xff).toByte())
        out.write("RIFF".toByteArray())
        out.write(le32(totalLen))
        out.write("WAVE".toByteArray())
        out.write("fmt ".toByteArray())
        out.write(le32(16))
        out.write(le16(1))          // PCM
        out.write(le16(1))          // mono
        out.write(le32(rate))
        out.write(le32(rate * 2))   // byte rate
        out.write(le16(2))          // block align
        out.write(le16(16))         // bits
        out.write("data".toByteArray())
        out.write(le32(dataLen))
        out.write(pcm)
        return out.toByteArray()
    }
}

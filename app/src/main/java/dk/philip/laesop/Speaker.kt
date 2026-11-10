package dk.philip.laesop

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Semaphore
import java.util.concurrent.atomic.AtomicInteger

/**
 * Laver tekst om til tale med Microsoft Azure og afspiller den.
 * Der findes kun én oplæser i hele appen (knap, widget, markeret tekst og test deler den).
 */
class Speaker private constructor(private val context: Context) {

    enum class State { IDLE, LOADING, PLAYING }

    companion object {
        @Volatile private var inst: Speaker? = null

        fun get(context: Context): Speaker =
            inst ?: synchronized(this) {
                inst ?: Speaker(context.applicationContext).also { inst = it }
            }
    }

    /** voice = stemmenavn, wrap = sprog til flersprogede stemmer (fx "da-DK") eller null. */
    private data class Chunk(val voice: String, val wrap: String?, val text: String)

    private val main = Handler(Looper.getMainLooper())
    private val generation = AtomicInteger(0)
    private val listeners = CopyOnWriteArrayList<(State) -> Unit>()
    private var player: MediaPlayer? = null
    private var gate: Semaphore? = null

    @Volatile var state = State.IDLE
        private set

    val isBusy: Boolean get() = state != State.IDLE

    fun addListener(l: (State) -> Unit) { listeners.add(l) }
    fun removeListener(l: (State) -> Unit) { listeners.remove(l) }

    private fun setState(s: State) {
        state = s
        main.post { for (l in listeners) l(s) }
    }

    fun speak(text: String, onError: (String) -> Unit) {
        stop()
        val settings = Settings(context)
        if (!settings.isReady) {
            onError("Skriv din Azure-nøgle og region i appen først.")
            return
        }
        val chunks = buildChunks(text, settings)
        if (chunks.isEmpty()) {
            onError("Der blev ikke fundet noget tekst at læse op.")
            return
        }

        val myGen = generation.incrementAndGet()
        val myGate = Semaphore(1)
        gate = myGate
        setState(State.LOADING)

        Thread {
            try {
                chunks.forEachIndexed { i, chunk ->
                    val file = synthesize(chunk, settings, i, myGen)
                    if (generation.get() != myGen) return@Thread
                    myGate.acquire()
                    if (generation.get() != myGen) return@Thread
                    main.post { play(file, myGate, myGen) }
                }
                myGate.acquire()
                if (generation.get() == myGen) setState(State.IDLE)
            } catch (e: Exception) {
                if (generation.get() == myGen) {
                    setState(State.IDLE)
                    val msg = e.message ?: "Ukendt fejl"
                    main.post { onError(msg) }
                }
            }
        }.start()
    }

    fun stop() {
        generation.incrementAndGet()
        try { player?.stop() } catch (_: Exception) {}
        player?.release()
        player = null
        gate?.release(10)
        gate = null
        if (state != State.IDLE) setState(State.IDLE)
    }

    private fun play(file: File, myGate: Semaphore, myGen: Int) {
        if (generation.get() != myGen) return
        player?.release()
        val mp = MediaPlayer()
        player = mp
        try {
            mp.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            mp.setDataSource(file.absolutePath)
            mp.setOnCompletionListener {
                file.delete()
                myGate.release()
            }
            mp.setOnErrorListener { _, _, _ ->
                myGate.release()
                true
            }
            mp.prepare()
            mp.start()
            setState(State.PLAYING)
        } catch (e: Exception) {
            myGate.release()
        }
    }

    // ---------- Azure ----------

    private fun synthesize(chunk: Chunk, s: Settings, index: Int, gen: Int): File {
        var result = request(ssml(chunk, s, true), s)
        // Hvis Azure ikke kan lide sprog-mærket, prøver vi igen uden
        if (result.first == 400 && chunk.wrap != null) {
            result = request(ssml(chunk, s, false), s)
        }
        val code = result.first
        val bytes = result.second
        if (code != 200 || bytes == null) {
            throw Exception(
                when (code) {
                    401 -> "Azure afviste nøglen (fejl 401). Tjek nøgle og region."
                    400 -> "Azure kunne ikke bruge stemmen (fejl 400). Tjek stemmenavnet."
                    429 -> "For mange forespørgsler til Azure lige nu (fejl 429). Prøv igen om lidt."
                    -1 -> "Ingen forbindelse til Azure. Tjek internettet."
                    else -> "Azure svarede med fejl $code."
                }
            )
        }
        val file = File(context.cacheDir, "tale_${gen}_$index.mp3")
        file.writeBytes(bytes)
        return file
    }

    private fun request(ssml: String, s: Settings): Pair<Int, ByteArray?> {
        return try {
            val url = URL("https://${s.region}.tts.speech.microsoft.com/cognitiveservices/v1")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 15000
            conn.readTimeout = 30000
            conn.doOutput = true
            conn.setRequestProperty("Ocp-Apim-Subscription-Key", s.key)
            conn.setRequestProperty("Content-Type", "application/ssml+xml")
            conn.setRequestProperty("X-Microsoft-OutputFormat", "audio-24khz-48kbitrate-mono-mp3")
            conn.setRequestProperty("User-Agent", "LaesOp")
            conn.outputStream.use { it.write(ssml.toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val bytes = if (code == 200) conn.inputStream.use { it.readBytes() } else null
            conn.disconnect()
            Pair(code, bytes)
        } catch (e: java.io.IOException) {
            Pair(-1, null)
        }
    }

    private fun ssml(c: Chunk, s: Settings, useWrap: Boolean): String {
        var body = escape(c.text)
        if (s.rate != 0) {
            val sign = if (s.rate > 0) "+" else ""
            body = "<prosody rate='$sign${s.rate}%'>$body</prosody>"
        }
        if (useWrap && c.wrap != null) {
            body = "<lang xml:lang='${c.wrap}'>$body</lang>"
        }
        return "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' " +
            "xml:lang='${Voices.locale(c.voice)}'>" +
            "<voice name='${escape(c.voice)}'>$body</voice></speak>"
    }

    private fun escape(t: String) = t
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "&apos;")
        .replace("\"", "&quot;")

    // ---------- Opdeling af tekst ----------

    private class Group(val voice: String, val wrap: String?, val sb: StringBuilder)

    /**
     * 1) Deler i linjer og gætter sproget for hver linje.
     * 2) Samler linjer, der skal læses med samme stemme og sprog.
     * 3) Deler lange stykker ved sætninger (under ca. 1500 tegn).
     */
    private fun buildChunks(text: String, s: Settings): List<Chunk> {
        val lines = text.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
        if (lines.isEmpty()) return emptyList()

        val multi = Voices.isMultilingual(s.voice)
        var current: Language.Lang? = null
        val groups = mutableListOf<Group>()

        for (line in lines) {
            if (s.autoLang) {
                val found = Language.detect(line)
                if (found != null) current = found
            }
            val isEn = current == Language.Lang.EN
            val voice: String
            val wrap: String?
            if (multi) {
                voice = s.voice
                wrap = if (!s.autoLang || current == null) null else if (isEn) "en-US" else "da-DK"
            } else {
                voice = if (s.autoLang && isEn) s.voiceEn else s.voice
                wrap = null
            }
            val last = groups.lastOrNull()
            if (last != null && last.voice == voice && last.wrap == wrap) {
                last.sb.append('\n').append(line)
            } else {
                groups.add(Group(voice, wrap, StringBuilder(line)))
            }
        }

        val out = mutableListOf<Chunk>()
        for (g in groups) {
            for (piece in splitBySentence(g.sb.toString())) out.add(Chunk(g.voice, g.wrap, piece))
        }

        // Første bid kort, så oplæsningen starter hurtigt
        if (out.isNotEmpty() && out[0].text.length > 300) {
            val first = out[0]
            val idx = first.text.indexOfAny(charArrayOf('.', '!', '?', '\n'), 80)
            if (idx in 1..400 && idx + 1 < first.text.length) {
                out[0] = first.copy(text = first.text.substring(0, idx + 1).trim())
                out.add(1, first.copy(text = first.text.substring(idx + 1).trim()))
            }
        }
        return out.filter { it.text.isNotBlank() }
    }

    private fun splitBySentence(text: String): List<String> {
        val parts = text.split(Regex("(?<=[.!?\\n])\\s+"))
        val out = mutableListOf<String>()
        val sb = StringBuilder()
        for (p in parts) {
            var piece = p
            while (piece.length > 1500) {
                if (sb.isNotEmpty()) { out.add(sb.toString()); sb.setLength(0) }
                out.add(piece.substring(0, 1500))
                piece = piece.substring(1500)
            }
            if (sb.length + piece.length + 1 > 1500 && sb.isNotEmpty()) {
                out.add(sb.toString()); sb.setLength(0)
            }
            if (sb.isNotEmpty()) sb.append(' ')
            sb.append(piece)
        }
        if (sb.isNotBlank()) out.add(sb.toString())
        return out
    }
}

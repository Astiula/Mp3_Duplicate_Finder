package pl.kondar.mp3duplicatefinder

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.documentfile.provider.DocumentFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.security.MessageDigest
import java.text.DecimalFormat

private data class Track(
    val uri: Uri, val name: String, val path: String, val size: Long,
    val artist: String, val title: String, val album: String, val bitrate: Long,
    val sha256: String, val duplicate: Boolean = false, val original: Boolean = false
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { FinderApp(this) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FinderApp(context: Context) {
    val prefs = remember { context.getSharedPreferences("finder", Context.MODE_PRIVATE) }
    var folderUri by remember { mutableStateOf(prefs.getString("tree_uri", null)?.let(Uri::parse)) }
    var tracks by remember { mutableStateOf<List<Track>>(emptyList()) }
    var selected by remember { mutableStateOf(setOf<String>()) }
    var scanning by remember { mutableStateOf(false) }
    var progress by remember { mutableFloatStateOf(0f) }
    var status by remember { mutableStateOf("Wybierz folder z muzyką, aby rozpocząć") }
    var dark by remember { mutableStateOf(prefs.getBoolean("dark", true)) }
    var showSettings by remember { mutableStateOf(false) }
    var apiKey by remember { mutableStateOf(prefs.getString("acoustid_key", "") ?: "") }
    var query by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val folderPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) {
            context.contentResolver.takePersistableUriPermission(uri, android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            folderUri = uri
            prefs.edit().putString("tree_uri", uri.toString()).apply()
            status = "Wybrano folder. Możesz rozpocząć skanowanie."
        }
    }
    val csvPicker = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri ->
        if (uri != null) {
            runCatching {
                context.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use { out ->
                    out.appendLine("filename;path;title;artist;album;size_bytes;bitrate;sha256;classification")
                    tracks.forEach { t ->
                        val values = listOf(t.name, t.path, t.title, t.artist, t.album, t.size.toString(), t.bitrate.toString(), t.sha256,
                            if (!t.duplicate) "BRAK DUPLIKATÓW" else if (t.original) "ORYGINAŁ" else "DUPLIKAT")
                        out.appendLine(values.joinToString(";") { "\"" + it.replace("\"", "\"\"") + "\"" })
                    }
                }
            }.onSuccess { status = "Zapisano CSV: " + uri.lastPathSegment }.onFailure { status = "Błąd eksportu CSV: " + it.message }
        }
    }

    val bg = if (dark) Color(0xFF0B1020) else Color(0xFFF2F5FB)
    val panel = if (dark) Color(0xCC19243A) else Color(0xDDFEFFFF)
    val fg = if (dark) Color(0xFFEAF1FF) else Color(0xFF17243A)
    val muted = if (dark) Color(0xFF9BAAC5) else Color(0xFF66758D)
    val accent = Color(0xFF71C7F2)

    MaterialTheme(colorScheme = if (dark) darkColorScheme(primary = accent, background = bg, surface = panel) else lightColorScheme(primary = Color(0xFF247FAE), background = bg, surface = panel)) {
        Box(Modifier.fillMaxSize().background(Brush.linearGradient(listOf(bg, if (dark) Color(0xFF1C3150) else Color(0xFFE1ECF8))))) {
            Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    Box(Modifier.size(44.dp).background(Brush.linearGradient(listOf(Color(0xFF67D5F5), Color(0xFF6D82E8))), CircleShape), contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.GraphicEq, null, tint = Color.White, modifier = Modifier.size(26.dp))
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("MP3 Duplicate Finder", color = fg, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                        Text("GLASSY MODERN  •  ANDROID", color = muted, fontSize = 10.sp, letterSpacing = 1.4.sp)
                    }
                    IconButton(onClick = { dark = !dark; prefs.edit().putBoolean("dark", dark).apply() }) {
                        Icon(if (dark) Icons.Rounded.LightMode else Icons.Rounded.DarkMode, "Motyw", tint = fg)
                    }
                    IconButton(onClick = { showSettings = true }) { Icon(Icons.Rounded.Settings, "Ustawienia", tint = fg) }
                }
                Spacer(Modifier.height(16.dp))
                GlassPanel(panel, Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Biblioteka muzyczna", color = fg, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                        Spacer(Modifier.height(6.dp))
                        Text(folderUri?.lastPathSegment ?: "Nie wybrano folderu", color = muted, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 12.sp)
                        Spacer(Modifier.height(12.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { folderPicker.launch(folderUri) }, modifier = Modifier.weight(1f)) {
                                Icon(Icons.Rounded.FolderOpen, null); Spacer(Modifier.width(5.dp)); Text("Folder")
                            }
                            OutlinedButton(enabled = folderUri != null && !scanning, onClick = {
                                val uri = folderUri ?: return@OutlinedButton
                                scanning = true; progress = 0f; status = "Przygotowywanie skanowania…"
                                tracks = emptyList()
                                selected = emptySet()
                                scope.launch {
                                    try {
                                        val result = scanFolder(context, uri) { p, message, scannedTrack ->
                                            progress = p
                                            status = message
                                            if (scannedTrack != null) {
                                                // Add each completed file immediately; duplicate labels are finalized after the scan.
                                                tracks = tracks + scannedTrack
                                            }
                                        }
                                        tracks = result
                                        selected = result.filter { it.duplicate && !it.original }.map { it.uri.toString() }.toSet()
                                        status = "Zakończono. Przeskanowano " + result.size + " plików."
                                    } catch (e: Exception) {
                                        status = "Błąd skanowania: " + (e.message ?: "nieznany błąd")
                                    } finally {
                                        scanning = false
                                    }
                                }
                            }, modifier = Modifier.weight(1f)) {
                                Icon(Icons.Rounded.Search, null); Spacer(Modifier.width(5.dp)); Text(if (scanning) "Skanuję…" else "Skanuj")
                            }
                        }
                        if (scanning) {
                            Spacer(Modifier.height(12.dp))
                            LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
                        }
                        Spacer(Modifier.height(8.dp))
                        Text(status, color = muted, fontSize = 12.sp)
                    }
                }
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatCard("PLIKI", tracks.size.toString(), panel, fg, muted, Modifier.weight(1f))
                    StatCard("DUPLIKATY", tracks.count { it.duplicate && !it.original }.toString(), panel, fg, muted, Modifier.weight(1f))
                    StatCard("ZAZNACZONE", selected.size.toString(), panel, fg, muted, Modifier.weight(1f))
                }
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(query, { query = it }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("Szukaj utworu lub ścieżki…") }, leadingIcon = { Icon(Icons.Rounded.Search, null) }, singleLine = true)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Wyniki analizy", color = fg, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                    TextButton(onClick = { selected = tracks.filter { it.duplicate && !it.original }.map { it.uri.toString() }.toSet() }) { Text("Zaznacz duplikaty") }
                }
                LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(tracks.filter { query.isBlank() || it.name.contains(query, true) || it.path.contains(query, true) || it.artist.contains(query, true) }, key = { it.uri.toString() }) { track ->
                        TrackRow(track, selected.contains(track.uri.toString()), panel, fg, muted) {
                            val key = track.uri.toString()
                            selected = if (selected.contains(key)) selected - key else selected + key
                        }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = { csvPicker.launch("mp3_duplicate_finder.csv") }, enabled = tracks.isNotEmpty(), modifier = Modifier.weight(1f)) {
                        Icon(Icons.Rounded.FileDownload, null); Spacer(Modifier.width(5.dp)); Text("Eksport CSV")
                    }
                    OutlinedButton(onClick = { selected = emptySet() }, enabled = selected.isNotEmpty(), modifier = Modifier.weight(1f)) {
                        Icon(Icons.Rounded.Deselect, null); Spacer(Modifier.width(5.dp)); Text("Odznacz")
                    }
                }
                Text("Android 1.0.0 • analiza SHA-256 (identyczne pliki)", color = muted, fontSize = 10.sp, modifier = Modifier.padding(top = 8.dp))
            }
        }
        if (showSettings) {
            AlertDialog(onDismissRequest = { showSettings = false }, title = { Text("Ustawienia") }, text = {
                Column {
                    Text("Klucz AcoustID", fontWeight = FontWeight.SemiBold)
                    OutlinedTextField(apiKey, { apiKey = it }, modifier = Modifier.fillMaxWidth(), singleLine = true, placeholder = { Text("Wklej API key") })
                    Spacer(Modifier.height(8.dp))
                    Text("Klucz jest przechowywany lokalnie w prywatnych ustawieniach aplikacji. Nie jest dołączany do APK.", fontSize = 12.sp)
                }
            }, confirmButton = { TextButton(onClick = { prefs.edit().putString("acoustid_key", apiKey.trim()).apply(); showSettings = false }) { Text("Zapisz") } },
                dismissButton = { TextButton(onClick = { showSettings = false }) { Text("Anuluj") } })
        }
    }
}

@Composable
private fun GlassPanel(color: Color, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.background(color, RoundedCornerShape(22.dp)).border(1.dp, Color.White.copy(alpha = 0.13f), RoundedCornerShape(22.dp)), content = content)
}

@Composable
private fun StatCard(label: String, value: String, panel: Color, fg: Color, muted: Color, modifier: Modifier) {
    GlassPanel(panel, modifier) {
        Column(Modifier.padding(12.dp)) {
            Text(label, color = muted, fontSize = 9.sp, letterSpacing = 1.sp)
            Text(value, color = fg, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun TrackRow(track: Track, checked: Boolean, panel: Color, fg: Color, muted: Color, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(panel, RoundedCornerShape(16.dp)).border(1.dp, Color.White.copy(alpha = .10f), RoundedCornerShape(16.dp)).clickable { onClick() }.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked, onCheckedChange = { onClick() })
        Column(Modifier.weight(1f)) {
            Text(track.title.ifBlank { track.name }, color = fg, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(listOf(track.artist, track.album).filter { it.isNotBlank() }.joinToString(" • ").ifBlank { track.path }, color = muted, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(if (!track.duplicate) "BRAK DUPLIKATÓW" else if (track.original) "ORYGINAŁ — grupa duplikatów" else "DUPLIKAT — identyczny plik", color = if (track.duplicate) Color(0xFFFFC56C) else Color(0xFF68CFA7), fontSize = 10.sp)
        }
        Text(DecimalFormat("0.0").format(track.size / 1048576.0) + " MB", color = muted, fontSize = 11.sp)
    }
}

private suspend fun scanFolder(
    context: Context,
    treeUri: Uri,
    onProgress: (Float, String, Track?) -> Unit
): List<Track> = withContext(Dispatchers.IO) {
    val root = DocumentFile.fromTreeUri(context, treeUri) ?: return@withContext emptyList()
    val files = mutableListOf<Pair<DocumentFile, String>>()
    fun walk(dir: DocumentFile, parent: String) {
        dir.listFiles().forEach { child ->
            val relative = if (parent.isBlank()) child.name.orEmpty() else parent + "/" + child.name.orEmpty()
            if (child.isDirectory) walk(child, relative)
            else if (child.name?.endsWith(".mp3", true) == true) files += child to relative
        }
    }
    walk(root, "")
    val raw = mutableListOf<Track>()
    files.forEachIndexed { index, pair ->
        val file = pair.first
        val message = "Analizuję " + (index + 1) + "/" + files.size + ": " + file.name
        val hash = runCatching { sha256(context, file.uri) }.getOrDefault("")
        val retriever = MediaMetadataRetriever()
        val track = runCatching {
            retriever.setDataSource(context, file.uri)
            Track(
                file.uri, file.name.orEmpty(), pair.second, file.length(),
                retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST).orEmpty(),
                retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE).orEmpty(),
                retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUM).orEmpty(),
                retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toLongOrNull() ?: 0L,
                hash
            )
        }.getOrNull()
        runCatching { retriever.release() }
        if (track != null) raw += track
        // Publish progress and the newly scanned file on the UI thread, not after the whole folder finishes.
        withContext(kotlinx.coroutines.Dispatchers.Main) {
            onProgress((index + 1f) / files.size.coerceAtLeast(1), message, track)
        }
    }
    val groups = raw.filter { it.sha256.isNotBlank() }.groupBy { it.sha256 }.filterValues { it.size > 1 }
    val marks = mutableMapOf<String, Pair<Boolean, Boolean>>()
    groups.values.forEach { group ->
        val original = group.maxWithOrNull(compareBy<Track> { it.bitrate }.thenBy { it.size }.thenBy { it.path })!!
        group.forEach { marks[it.uri.toString()] = (it.uri == original.uri) to true }
    }
    raw.map { track ->
        val mark = marks[track.uri.toString()]
        if (mark == null) track else track.copy(original = mark.first, duplicate = true)
    }
}

private fun sha256(context: Context, uri: Uri): String {
    val digest = MessageDigest.getInstance("SHA-256")
    context.contentResolver.openInputStream(uri)!!.use { input ->
        val buffer = ByteArray(256 * 1024)
        while (true) { val n = input.read(buffer); if (n <= 0) break; digest.update(buffer, 0, n) }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}

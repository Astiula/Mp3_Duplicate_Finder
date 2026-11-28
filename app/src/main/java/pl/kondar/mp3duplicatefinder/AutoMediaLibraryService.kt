package pl.kondar.mp3duplicatefinder

import android.net.Uri
import android.os.Bundle
import androidx.documentfile.provider.DocumentFile
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.LibraryResult
import androidx.media3.session.MediaLibraryService
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture

/**
 * Media3 library exposed to Android Auto. It browses the folder selected in
 * the phone app and streams the original MP3 documents through their SAF URIs.
 */
class AutoMediaLibraryService : MediaLibraryService() {
    private var librarySession: MediaLibrarySession? = null

    override fun onCreate() {
        super.onCreate()
        val player = ExoPlayer.Builder(this).build().apply {
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(C.USAGE_MEDIA)
                    .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                    .build(),
                true
            )
            setHandleAudioBecomingNoisy(true)
        }
        val callback = object : MediaLibrarySession.Callback {
            override fun onGetLibraryRoot(
                session: MediaLibrarySession,
                browser: MediaSession.ControllerInfo,
                params: LibraryParams?
            ): ListenableFuture<LibraryResult<MediaItem>> {
                val root = MediaItem.Builder()
                    .setMediaId(ROOT_ID)
                    .setMediaMetadata(
                        MediaMetadata.Builder()
                            .setTitle("MP3 Duplicate Finder")
                            .setIsBrowsable(true)
                            .setIsPlayable(false)
                            .build()
                    ).build()
                return Futures.immediateFuture(LibraryResult.ofItem(root, params))
            }

            override fun onGetChildren(
                session: MediaLibrarySession,
                browser: MediaSession.ControllerInfo,
                parentId: String,
                page: Int,
                pageSize: Int,
                params: LibraryParams?
            ): ListenableFuture<LibraryResult<MutableList<MediaItem>>> {
                if (parentId != ROOT_ID) {
                    return Futures.immediateFuture(LibraryResult.ofItemList(mutableListOf(), params))
                }
                val items = loadTracks()
                val from = (page * pageSize).coerceAtMost(items.size)
                val to = (from + pageSize).coerceAtMost(items.size)
                return Futures.immediateFuture(LibraryResult.ofItemList(items.subList(from, to).toMutableList(), params))
            }

            override fun onGetItem(
                session: MediaLibrarySession,
                browser: MediaSession.ControllerInfo,
                mediaId: String
            ): ListenableFuture<LibraryResult<MediaItem>> {
                val item = loadTracks().firstOrNull { it.mediaId == mediaId }
                    ?: return Futures.immediateFuture(LibraryResult.ofError(LibraryResult.RESULT_ERROR_BAD_VALUE))
                return Futures.immediateFuture(LibraryResult.ofItem(item, null))
            }
        }
        librarySession = MediaLibrarySession.Builder(this, player, callback).build()
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaLibrarySession? = librarySession

    override fun onDestroy() {
        librarySession?.run {
            player.release()
            release()
        }
        librarySession = null
        super.onDestroy()
    }

    private fun loadTracks(): List<MediaItem> {
        val tree = getSharedPreferences("finder", MODE_PRIVATE).getString("tree_uri", null)
            ?.let(Uri::parse) ?: return emptyList()
        val root = DocumentFile.fromTreeUri(this, tree) ?: return emptyList()
        val result = mutableListOf<MediaItem>()
        fun walk(directory: DocumentFile) {
            directory.listFiles().forEach { file ->
                if (file.isDirectory) walk(file)
                else if (file.name?.endsWith(".mp3", ignoreCase = true) == true && file.canRead()) {
                    val retriever = android.media.MediaMetadataRetriever()
                    val (title, artist, album) = runCatching {
                        retriever.setDataSource(this, file.uri)
                        Triple(
                            retriever.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_TITLE).orEmpty().ifBlank { file.name.orEmpty() },
                            retriever.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_ARTIST).orEmpty(),
                            retriever.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_ALBUM).orEmpty()
                        )
                    }.getOrElse { Triple(file.name.orEmpty(), "", "") }
                    runCatching { retriever.release() }
                    val metadata = MediaMetadata.Builder()
                        .setTitle(title)
                        .setArtist(artist)
                        .setAlbumTitle(album)
                        .setIsBrowsable(false)
                        .setIsPlayable(true)
                        .setMediaType(MediaMetadata.MEDIA_TYPE_MUSIC)
                        .build()
                    result += MediaItem.Builder()
                        .setMediaId(file.uri.toString())
                        .setUri(file.uri)
                        .setMimeType("audio/mpeg")
                        .setMediaMetadata(metadata)
                        .build()
                }
            }
        }
        runCatching { walk(root) }
        return result.sortedBy { it.mediaMetadata.title?.toString()?.lowercase().orEmpty() }
    }

    companion object {
        private const val ROOT_ID = "mp3_duplicate_finder_root"
    }
}

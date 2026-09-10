package com.tcpfacturador.cliente

import android.content.Context
import android.provider.Settings
import com.google.gson.annotations.SerializedName
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*

// ---------- modelos (.respuestas API) ----------
data class RespRegistro(
    val ok: Boolean, val token: String? = null, val codigo: String? = null,
    val estado: String? = null, val mensaje: String? = null, val error: String? = null
)
data class RespEstado(
    val ok: Boolean, val codigo: String? = null, val estado: String? = null,
    val docs: Int = 0, val plan_fin: String? = null, val activo: Boolean = false,
    val en_gracia: Boolean = false, val mensaje: String? = null, val error: String? = null
)
data class ClienteFinal(
    val id: Int, val empresa: String,
    val cuenta_cup: String? = null, val cuenta_cuc: String? = null,
    val agencia: String? = null, val codigo: String? = null, val nit: String? = null,
    val telefono_whatsapp: String? = null, val direccion: String? = null
)
data class RespClientes(val ok: Boolean, val clientes: List<ClienteFinal> = emptyList())
data class ItemDoc(val descripcion: String, val um: String = "U", val cantidad: Double, val precio: Double)
data class ReqDoc(
    val tipo: String, val cliente_final_id: Int = 0, val contrato_no: String = "",
    val fecha: String? = null, val numero_blanco: Boolean = false,
    val fecha_blanco: Boolean = false, val items: List<ItemDoc>
)
data class RespDoc(
    val ok: Boolean, val doc_id: Int? = null, val estado: String? = null,
    val mensaje: String? = null, val error: String? = null,
    val docs_restantes: Int? = null, val requiere_recarga: Boolean = false
)
data class DocInfo(
    val id: Int, val numero: String? = null, val tipo: String = "",
    val estado: String = "", val total: Double = 0.0, val total_txt: String = "",
    val fecha: String? = null, val empresa: String? = null, val pdf: Boolean = false
)
data class RespDocs(val ok: Boolean, val documentos: List<DocInfo> = emptyList())
data class Aviso(
    val id: Int, val titulo: String, val mensaje: String,
    val tipo: String? = null, val leida: Int = 0, val created_at: String = ""
)
data class RespAvisos(val ok: Boolean, val notificaciones: List<Aviso> = emptyList())
data class RespOk(val ok: Boolean, val error: String? = null)

// ---------- servicio Retrofit ----------
interface ApiService {
    @POST("api/registro")
    suspend fun registro(@Body d: Map<String, String?>): RespRegistro

    @POST("api/estado")
    suspend fun estado(
        @Header("X-Token") token: String,
        @Header("X-Device") device: String
    ): RespEstado

    @GET("api/mis-clientes")
    suspend fun misClientes(
        @Header("X-Token") token: String,
        @Header("X-Device") device: String
    ): RespClientes

    @POST("api/solicitar-documento")
    suspend fun solicitar(
        @Header("X-Token") token: String,
        @Header("X-Device") device: String,
        @Body d: ReqDoc
    ): RespDoc

    @GET("api/mis-documentos")
    suspend fun misDocumentos(
        @Header("X-Token") token: String,
        @Header("X-Device") device: String
    ): RespDocs

    @GET("api/documentos/{id}/pdf")
    @Streaming
    suspend fun pdf(
        @Header("X-Token") token: String,
        @Header("X-Device") device: String,
        @Path("id") id: Int
    ): Response<ResponseBody>

    @GET("api/notificaciones")
    suspend fun avisos(
        @Header("X-Token") token: String,
        @Header("X-Device") device: String
    ): RespAvisos

    @POST("api/notificaciones/leer")
    suspend fun avisosLeer(
        @Header("X-Token") token: String,
        @Header("X-Device") device: String
    ): RespOk
}

// ---------- sesion local (token + telefono) ----------
object Sesion {
    private const val P = "tcp_cli"
    fun deviceId(ctx: Context): String =
        Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ANDROID_ID) ?: "SIN-ID"

    fun token(ctx: Context): String =
        ctx.getSharedPreferences(P, Context.MODE_PRIVATE).getString("token", "") ?: ""

    fun guardarToken(ctx: Context, t: String) {
        ctx.getSharedPreferences(P, Context.MODE_PRIVATE).edit().putString("token", t).apply()
    }

    fun borrar(ctx: Context) {
        ctx.getSharedPreferences(P, Context.MODE_PRIVATE).edit().clear().apply()
    }
}

// ---------- cliente Retrofit ----------
object Api {
    @Volatile private var svc: ApiService? = null
    fun svc(): ApiService {
        svc?.let { return it }
        synchronized(this) {
            svc?.let { return it }
            val log = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
            val cli = OkHttpClient.Builder().addInterceptor(log).build()
            val r = Retrofit.Builder()
                .baseUrl(BuildConfig.SERVER_URL.trimEnd('/') + "/")
                .client(cli)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
            val s = r.create(ApiService::class.java)
            svc = s
            return s
        }
    }
}

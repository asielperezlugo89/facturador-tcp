package com.tcpfacturador.admin

import android.content.Context
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*

// ---------- modelos ----------
interface ApiResponse { val ok: Boolean; val error: String? }
data class RespLogin(val ok: Boolean, val token: String? = null, val error: String? = null)

data class Resumen(
    val tcp_total: Int = 0, val tcp_activos: Int = 0, val tcp_pendientes: Int = 0,
    val solicitudes: Int = 0, val enviados: Int = 0, val cobrado: Double = 0.0,
    val notif_no_leidas: Int = 0
)
data class RespResumen(val ok: Boolean, val resumen: Resumen? = null, val error: String? = null)

data class TcpInfo(
    val id: Int, val codigo: String = "", val nombre_apellidos: String = "",
    val ci: String = "", val telefono: String = "", val direccion: String = "",
    val email: String = "", val cuenta_cup: String = "", val agencia: String = "",
    val codigo_barra: String = "", val nit: String = "", val cargo: String = "TCP",
    val device_id: String = "", val estado: String = "",
    val docs_disponibles: Int = 0, val plan_inicio: String = "",
    val plan_fin: String = "", val created_at: String = ""
)
data class RespTcp(val ok: Boolean, val tcp: List<TcpInfo> = emptyList(), val error: String? = null)
data class RespTcpOne(val ok: Boolean, val tcp: TcpInfo? = null, val error: String? = null)
data class RespId(override val ok: Boolean, val tcp_id: Int? = null, val cliente_id: Int? = null, override val error: String? = null) : ApiResponse

data class ItemDoc(val descripcion: String, val um: String = "U", val cantidad: Double, val precio: Double)
data class Solicitud(
    val id: Int, val numero: String = "", val tipo: String = "",
    val estado: String = "", val contrato_no: String = "", val fecha: String = "",
    val items: List<ItemDoc> = emptyList(), val created_at: String = "",
    val codigo: String = "", val nombre_apellidos: String = "", val empresa: String = ""
)
data class RespSolicitudes(val ok: Boolean, val solicitudes: List<Solicitud> = emptyList(), val error: String? = null)

data class DocInfo(
    val id: Int, val numero: String = "", val tipo: String = "",
    val estado: String = "", val total: Double = 0.0, val total_txt: String = "",
    val fecha: String = "", val contrato_no: String = "", val created_at: String = "",
    val codigo: String = "", val empresa: String = "", val pdf: Boolean = false
)
data class RespDocs(val ok: Boolean, val documentos: List<DocInfo> = emptyList(), val error: String? = null)

data class ClienteFinal(
    val id: Int, val tcp_id: Int = 0, val empresa: String = "",
    val cuenta_cup: String = "", val cuenta_cuc: String = "",
    val agencia: String = "", val codigo: String = "", val nit: String = "",
    val telefono_whatsapp: String = "", val direccion: String = "",
    val notas: String = "", val created_at: String = ""
)
data class RespClientes(val ok: Boolean, val clientes: List<ClienteFinal> = emptyList(), val error: String? = null)

data class Recarga(
    val id: Int, val tcp_id: Int = 0, val tipo: String = "",
    val docs: Int = 0, val monto: Double = 0.0, val monto_txt: String = "",
    val fecha: String = "", val admin: String = "", val nota: String = "",
    val codigo: String = ""
)
data class RespRecargas(val ok: Boolean, val recargas: List<Recarga> = emptyList(), val error: String? = null)

data class Aviso(
    val id: Int, val titulo: String = "", val mensaje: String = "",
    val tipo: String = "", val leida: Int = 0, val created_at: String = "",
    val extra: String = ""
)
data class RespAvisos(val ok: Boolean, val notificaciones: List<Aviso> = emptyList(), val error: String? = null)

data class RespConfig(
    val ok: Boolean, val config: Map<String, String> = emptyMap(), val error: String? = null
)

data class RespOk(override val ok: Boolean, val mensaje: String? = null, override val error: String? = null) : ApiResponse

// ---------- servicio Retrofit ----------
interface AdminApiService {
    @POST("api/admin/login")
    suspend fun login(@Body d: Map<String, String>): RespLogin

    @GET("api/admin/resumen")
    suspend fun resumen(@Header("X-Admin-Token") token: String): RespResumen

    @GET("api/admin/tcp")
    suspend fun tcpList(@Header("X-Admin-Token") token: String): RespTcp

    @POST("api/admin/tcp")
    suspend fun tcpCreate(@Header("X-Admin-Token") token: String, @Body d: Map<String, String?>): RespId

    @GET("api/admin/tcp/{id}")
    suspend fun tcpGet(@Header("X-Admin-Token") token: String, @Path("id") id: Int): RespTcpOne

    @PUT("api/admin/tcp/{id}")
    suspend fun tcpUpdate(@Header("X-Admin-Token") token: String, @Path("id") id: Int, @Body d: Map<String, String?>): RespOk

    @POST("api/admin/activar/{id}")
    suspend fun tcpActivar(@Header("X-Admin-Token") token: String, @Path("id") id: Int, @Body d: Map<String, String> = emptyMap()): RespOk

    @POST("api/admin/tcp/{id}/suspender")
    suspend fun tcpSuspender(@Header("X-Admin-Token") token: String, @Path("id") id: Int): RespOk

    @retrofit2.http.DELETE("api/admin/tcp/{id}")
    suspend fun tcpDelete(@Header("X-Admin-Token") token: String, @Path("id") id: Int): RespOk

    @POST("api/admin/tcp/{id}/imagen")
    suspend fun tcpImagen(@Header("X-Admin-Token") token: String, @Path("id") id: Int, @Body d: Map<String, String?>): RespOk

    @GET("api/admin/solicitudes")
    suspend fun solicitudes(@Header("X-Admin-Token") token: String): RespSolicitudes

    @POST("api/admin/generar/{id}")
    suspend fun generar(@Header("X-Admin-Token") token: String, @Path("id") id: Int): RespOk

    @GET("api/admin/documentos")
    suspend fun docsList(@Header("X-Admin-Token") token: String, @Query("estado") estado: String? = null, @Query("tcp") tcp: Int? = null): RespDocs

    @POST("api/admin/documentos")
    suspend fun docsCreate(@Header("X-Admin-Token") token: String, @Body d: Any): RespOk

    @POST("api/admin/documentos/{id}/anular")
    suspend fun docsAnular(@Header("X-Admin-Token") token: String, @Path("id") id: Int): RespOk

    @retrofit2.http.DELETE("api/admin/documentos/{id}")
    suspend fun docsDelete(@Header("X-Admin-Token") token: String, @Path("id") id: Int): RespOk

    @GET("api/admin/documentos/{id}/pdf")
    @Streaming
    suspend fun docsPdf(@Header("X-Admin-Token") token: String, @Path("id") id: Int): Response<ResponseBody>

    @GET("api/admin/clientes")
    suspend fun clientesList(@Header("X-Admin-Token") token: String, @Query("tcp") tcp: Int? = null): RespClientes

    @POST("api/admin/clientes")
    suspend fun clientesCreate(@Header("X-Admin-Token") token: String, @Body d: Map<String, String?>): RespId

    @PUT("api/admin/clientes/{id}")
    suspend fun clientesUpdate(@Header("X-Admin-Token") token: String, @Path("id") id: Int, @Body d: Map<String, String?>): RespOk

    @retrofit2.http.DELETE("api/admin/clientes/{id}")
    suspend fun clientesDelete(@Header("X-Admin-Token") token: String, @Path("id") id: Int): RespOk

    @GET("api/admin/recargas")
    suspend fun recargas(@Header("X-Admin-Token") token: String): RespRecargas

    @GET("api/admin/notificaciones")
    suspend fun avisos(@Header("X-Admin-Token") token: String): RespAvisos

    @GET("api/admin/config")
    suspend fun configGet(@Header("X-Admin-Token") token: String): RespConfig

    @PUT("api/admin/config")
    suspend fun configPut(@Header("X-Admin-Token") token: String, @Body d: Map<String, String?>): RespOk

    @POST("api/admin/password")
    suspend fun password(@Header("X-Admin-Token") token: String, @Body d: Map<String, String>): RespOk
}

// ---------- sesion local ----------
object Sesion {
    private const val P = "tcp_admin"
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
    @Volatile private var svc: AdminApiService? = null
    fun svc(): AdminApiService {
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
            val s = r.create(AdminApiService::class.java)
            svc = s
            return s
        }
    }
}

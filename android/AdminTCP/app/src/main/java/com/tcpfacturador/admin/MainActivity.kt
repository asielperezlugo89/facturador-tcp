package com.tcpfacturador.admin

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream

class MainActivity : AppCompatActivity() {

    private lateinit var token: String
    private lateinit var container: FrameLayout
    private lateinit var bottomNav: LinearLayout
    private var currentTab = "sol"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        token = Sesion.token(this)
        if (token.isEmpty()) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }

        // Barra de resumen
        val tvResumen = TextView(this).apply {
            setPadding(16, 12, 16, 12)
            setBackgroundColor(0xFF0d9488.toInt())
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 13f
        }
        root.addView(tvResumen)

        // Contenedor de contenido
        container = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        root.addView(container)

        // Bottom navigation
        bottomNav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(0xFF0f172a.toInt())
            setPadding(0, 4, 0, 4)
        }
        root.addView(bottomNav)

        val tabs = listOf(
            Triple("sol", "Solicitudes", "📥"),
            Triple("tcp", "TCP", "👥"),
            Triple("cli", "Clientes", "🏢"),
            Triple("doc", "Docs", "📑"),
            Triple("mas", "Más", "⚙️")
        )

        for ((id, label, icon) in tabs) {
            val btn = Button(this).apply {
                text = "$icon\n$label"
                setTextColor(0xFFFFFFFF.toInt())
                setBackgroundColor(0x00000000)
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                textSize = 10f
                setOnClickListener { selectTab(id) }
                tag = id
            }
            bottomNav.addView(btn)
        }

        setContentView(root)
        selectTab("sol")
        refreshResumen(tvResumen)
    }

    private fun selectTab(id: String) {
        currentTab = id
        container.removeAllViews()
        when (id) {
            "sol" -> loadSolicitudes()
            "tcp" -> loadTcp()
            "cli" -> loadClientes()
            "doc" -> loadDocs()
            "mas" -> loadMas()
        }
    }

    private fun refreshResumen(tv: TextView) {
        lifecycleScope.launch {
            try {
                val resp = Api.svc().resumen(token)
                if (resp.ok && resp.resumen != null) {
                    val r = resp.resumen
                    tv.text = "TCP: ${r.tcp_total} total, ${r.tcp_activos} activos, ${r.tcp_pendientes} pendientes | Enviados: ${r.enviados} | Cobrado: ${r.cobrado} CUP"
                }
            } catch (_: Exception) {}
        }
    }

    // ==================== SOLICITUDES ====================
    private fun loadSolicitudes() {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(16, 16, 16, 16) }
        val tvEmpty = TextView(this).apply { text = "Cargando..."; setPadding(0, 32, 0, 0) }
        layout.addView(tvEmpty)
        scroll.addView(layout)
        container.addView(scroll)

        lifecycleScope.launch {
            try {
                val resp = Api.svc().solicitudes(token)
                layout.removeAllViews()
                if (resp.ok && resp.solicitudes.isNotEmpty()) {
                    for (s in resp.solicitudes) {
                        layout.addView(createCard(
                            "#${s.id} ${s.tipo.uppercase()} · ${s.codigo} ${s.nombre_apellidos}",
                            "Cliente: ${s.empresa}\nContrato: ${s.contrato_no}\nArtículos: ${s.items.joinToString { "${it.descripcion} x${it.cantidad} @${it.precio}" }}",
                            listOf(
                                "⚡ Generar" to { generarDoc(s.id, layout) },
                                "Anular" to { anularDoc(s.id, layout) }
                            )
                        ))
                    }
                } else {
                    tvEmpty.text = "No hay solicitudes pendientes"
                    layout.addView(tvEmpty)
                }
            } catch (e: Exception) {
                tvEmpty.text = "Error: ${e.message}"
            }
        }
    }

    private fun generarDoc(id: Int, layout: LinearLayout) {
        AlertDialog.Builder(this)
            .setTitle("Generar documento")
            .setMessage("Se descargará 1 documento del saldo del TCP. ¿Continuar?")
            .setPositiveButton("Generar") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = Api.svc().generar(token, id)
                        Toast.makeText(this@MainActivity, resp.mensaje ?: resp.error ?: "Listo", Toast.LENGTH_SHORT).show()
                        if (resp.ok) loadSolicitudes()
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun anularDoc(id: Int, layout: LinearLayout) {
        AlertDialog.Builder(this)
            .setTitle("Anular documento")
            .setMessage("Esta acción no se puede deshacer. ¿Continuar?")
            .setPositiveButton("Anular") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = Api.svc().docsAnular(token, id)
                        Toast.makeText(this@MainActivity, if (resp.ok) "Anulado" else (resp.error ?: "Error"), Toast.LENGTH_SHORT).show()
                        if (resp.ok) loadSolicitudes()
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    // ==================== TCP ====================
    private fun loadTcp() {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(16, 16, 16, 16) }

        val btnNuevo = Button(this).apply {
            text = "+ Nuevo TCP"
            setOnClickListener { showTcpForm(null, layout) }
        }
        layout.addView(btnNuevo)

        val tvEmpty = TextView(this).apply { text = "Cargando..."; setPadding(0, 16, 0, 0) }
        layout.addView(tvEmpty)
        scroll.addView(layout)
        container.addView(scroll)

        lifecycleScope.launch {
            try {
                val resp = Api.svc().tcpList(token)
                layout.removeView(tvEmpty)
                if (resp.ok && resp.tcp.isNotEmpty()) {
                    for (t in resp.tcp) {
                        val estadoColor = when (t.estado) {
                            "activo" -> 0xFF4CAF50.toInt()
                            "pendiente" -> 0xFFFFC107.toInt()
                            "suspendido" -> 0xFFF44336.toInt()
                            else -> 0xFF9E9E9E.toInt()
                        }
                        layout.addView(createCard(
                            "${t.codigo} ${t.nombre_apellidos} [${t.estado}]",
                            "Docs: ${t.docs_disponibles} · Vence: ${t.plan_fin} · Tel: ${t.telefono}",
                            buildList {
                                if (t.estado != "activo") add("⚡ Plan" to { activarTcp(t.id, "plan", layout) })
                                add("+ Extra" to { activarTcp(t.id, "extra", layout) })
                                add("✏️ Editar" to { showTcpForm(t, layout) })
                                if (t.estado == "activo" || t.estado == "gracia") add("Suspender" to { suspenderTcp(t.id, layout) })
                                add("Eliminar" to { eliminarTcp(t.id, layout) })
                            }
                        ))
                    }
                } else {
                    tvEmpty.text = "No hay TCP registrados"
                    layout.addView(tvEmpty)
                }
            } catch (e: Exception) {
                tvEmpty.text = "Error: ${e.message}"
            }
        }
    }

    private fun activarTcp(id: Int, modo: String, layout: LinearLayout) {
        val label = if (modo == "extra") "recarga extra (+50 docs)" else "plan base (100 docs / 30 días)"
        AlertDialog.Builder(this)
            .setTitle("Activar TCP")
            .setMessage("Activar $label?")
            .setPositiveButton("Activar") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = Api.svc().tcpActivar(token, id, mapOf("modo" to modo))
                        Toast.makeText(this@MainActivity, resp.mensaje ?: resp.error ?: "Listo", Toast.LENGTH_SHORT).show()
                        if (resp.ok) loadTcp()
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun suspenderTcp(id: Int, layout: LinearLayout) {
        AlertDialog.Builder(this)
            .setTitle("Suspender TCP")
            .setMessage("¿Suspender esta cuenta?")
            .setPositiveButton("Suspender") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = Api.svc().tcpSuspender(token, id)
                        Toast.makeText(this@MainActivity, resp.mensaje ?: "Suspendido", Toast.LENGTH_SHORT).show()
                        loadTcp()
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun eliminarTcp(id: Int, layout: LinearLayout) {
        AlertDialog.Builder(this)
            .setTitle("Eliminar TCP")
            .setMessage("Se eliminará el TCP junto con todos sus documentos y clientes. ¿Continuar?")
            .setPositiveButton("Eliminar") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = Api.svc().tcpDelete(token, id)
                        Toast.makeText(this@MainActivity, if (resp.ok) "Eliminado" else (resp.error ?: "Error"), Toast.LENGTH_SHORT).show()
                        if (resp.ok) loadTcp()
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun showTcpForm(tcp: TcpInfo?, reloadLayout: LinearLayout) {
        val dialog = AlertDialog.Builder(this)
        val formLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 16, 32, 16) }

        val etNombre = EditText(this).apply { hint = "Nombre *"; setText(tcp?.nombre_apellidos ?: "") }
        val etCi = EditText(this).apply { hint = "CI"; setText(tcp?.ci ?: "") }
        val etTel = EditText(this).apply { hint = "Teléfono"; setText(tcp?.telefono ?: "") }
        val etDir = EditText(this).apply { hint = "Dirección"; setText(tcp?.direccion ?: "") }
        val etCup = EditText(this).apply { hint = "Cuenta CUP"; setText(tcp?.cuenta_cup ?: "") }
        val etNit = EditText(this).apply { hint = "NIT"; setText(tcp?.nit ?: "") }
        val etAgencia = EditText(this).apply { hint = "Agencia"; setText(tcp?.agencia ?: "") }

        for (et in listOf(etNombre, etCi, etTel, etDir, etCup, etNit, etAgencia)) formLayout.addView(et)

        dialog.setView(formLayout)
        dialog.setPositiveButton("Guardar") { _, _ ->
            val data = mutableMapOf<String, String?>(
                "nombre_apellidos" to etNombre.text.toString().trim(),
                "ci" to etCi.text.toString().trim(),
                "telefono" to etTel.text.toString().trim(),
                "direccion" to etDir.text.toString().trim(),
                "cuenta_cup" to etCup.text.toString().trim(),
                "nit" to etNit.text.toString().trim(),
                "agencia" to etAgencia.text.toString().trim()
            )
            if (data["nombre_apellidos"].isNullOrEmpty()) {
                Toast.makeText(this, "El nombre es obligatorio", Toast.LENGTH_SHORT).show()
                return@setPositiveButton
            }
            lifecycleScope.launch {
                try {
                    val resp = if (tcp != null) {
                        Api.svc().tcpUpdate(token, tcp.id, data)
                    } else {
                        Api.svc().tcpCreate(token, data)
                    }
                    Toast.makeText(this@MainActivity, if (resp.ok) "Guardado" else (resp.error ?: "Error"), Toast.LENGTH_SHORT).show()
                    if (resp.ok) loadTcp()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
        dialog.setNegativeButton("Cancelar", null)
        dialog.show()
    }

    // ==================== CLIENTES ====================
    private fun loadClientes() {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(16, 16, 16, 16) }

        val btnNuevo = Button(this).apply {
            text = "+ Nuevo Cliente"
            setOnClickListener { showClienteForm(null, layout) }
        }
        layout.addView(btnNuevo)

        val tvEmpty = TextView(this).apply { text = "Cargando..."; setPadding(0, 16, 0, 0) }
        layout.addView(tvEmpty)
        scroll.addView(layout)
        container.addView(scroll)

        lifecycleScope.launch {
            try {
                val resp = Api.svc().clientesList(token)
                layout.removeView(tvEmpty)
                if (resp.ok && resp.clientes.isNotEmpty()) {
                    for (c in resp.clientes) {
                        layout.addView(createCard(
                            "${c.empresa} (${c.codigo})",
                            "WA: ${c.telefono_whatsapp} · NIT: ${c.nit}\nCUP: ${c.cuenta_cup} · Agencia: ${c.agencia}",
                            listOf(
                                "✏️ Editar" to { showClienteForm(c, layout) },
                                "Eliminar" to { eliminarCliente(c.id, layout) }
                            )
                        ))
                    }
                } else {
                    tvEmpty.text = "No hay clientes registrados"
                    layout.addView(tvEmpty)
                }
            } catch (e: Exception) {
                tvEmpty.text = "Error: ${e.message}"
            }
        }
    }

    private fun showClienteForm(cliente: ClienteFinal?, reloadLayout: LinearLayout) {
        val dialog = AlertDialog.Builder(this)
        val formLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 16, 32, 16) }

        val etEmpresa = EditText(this).apply { hint = "Empresa *"; setText(cliente?.empresa ?: "") }
        val etCup = EditText(this).apply { hint = "Cuenta CUP"; setText(cliente?.cuenta_cup ?: "") }
        val etCuc = EditText(this).apply { hint = "Cuenta CUC"; setText(cliente?.cuenta_cuc ?: "") }
        val etAgencia = EditText(this).apply { hint = "Agencia"; setText(cliente?.agencia ?: "") }
        val etCodigo = EditText(this).apply { hint = "Código"; setText(cliente?.codigo ?: "") }
        val etNit = EditText(this).apply { hint = "NIT"; setText(cliente?.nit ?: "") }
        val etWa = EditText(this).apply { hint = "WhatsApp"; setText(cliente?.telefono_whatsapp ?: "") }
        val etDir = EditText(this).apply { hint = "Dirección"; setText(cliente?.direccion ?: "") }

        for (et in listOf(etEmpresa, etCup, etCuc, etAgencia, etCodigo, etNit, etWa, etDir)) formLayout.addView(et)

        dialog.setView(formLayout)
        dialog.setPositiveButton("Guardar") { _, _ ->
            val data = mutableMapOf<String, String?>(
                "empresa" to etEmpresa.text.toString().trim(),
                "cuenta_cup" to etCup.text.toString().trim(),
                "cuenta_cuc" to etCuc.text.toString().trim(),
                "agencia" to etAgencia.text.toString().trim(),
                "codigo" to etCodigo.text.toString().trim(),
                "nit" to etNit.text.toString().trim(),
                "telefono_whatsapp" to etWa.text.toString().trim(),
                "direccion" to etDir.text.toString().trim()
            )
            if (data["empresa"].isNullOrEmpty()) {
                Toast.makeText(this, "La empresa es obligatoria", Toast.LENGTH_SHORT).show()
                return@setPositiveButton
            }
            lifecycleScope.launch {
                try {
                    val resp = if (cliente != null) {
                        Api.svc().clientesUpdate(token, cliente.id, data)
                    } else {
                        data["tcp_id"] = "1"
                        Api.svc().clientesCreate(token, data)
                    }
                    Toast.makeText(this@MainActivity, if (resp.ok) "Guardado" else (resp.error ?: "Error"), Toast.LENGTH_SHORT).show()
                    if (resp.ok) loadClientes()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
        dialog.setNegativeButton("Cancelar", null)
        dialog.show()
    }

    private fun eliminarCliente(id: Int, layout: LinearLayout) {
        AlertDialog.Builder(this)
            .setTitle("Eliminar cliente")
            .setMessage("¿Eliminar este cliente permanentemente?")
            .setPositiveButton("Eliminar") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = Api.svc().clientesDelete(token, id)
                        Toast.makeText(this@MainActivity, if (resp.ok) "Eliminado" else (resp.error ?: "Error"), Toast.LENGTH_SHORT).show()
                        if (resp.ok) loadClientes()
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    // ==================== DOCUMENTOS ====================
    private fun loadDocs() {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(16, 16, 16, 16) }

        val tvEmpty = TextView(this).apply { text = "Cargando..."; setPadding(0, 16, 0, 0) }
        layout.addView(tvEmpty)
        scroll.addView(layout)
        container.addView(scroll)

        lifecycleScope.launch {
            try {
                val resp = Api.svc().docsList(token)
                layout.removeAllViews()
                if (resp.ok && resp.documentos.isNotEmpty()) {
                    for (d in resp.documentos) {
                        val estadoColor = when (d.estado) {
                            "enviado" -> 0xFF4CAF50.toInt()
                            "solicitado" -> 0xFFFFC107.toInt()
                            "anulado" -> 0xFFF44336.toInt()
                            else -> 0xFF9E9E9E.toInt()
                        }
                        layout.addView(createCard(
                            "#${d.id} ${d.numero} ${d.tipo} [${d.estado}]",
                            "${d.codigo} · ${d.empresa} · ${d.total_txt} CUP",
                            buildList {
                                if (d.pdf) add("📄 PDF" to { downloadPdf(d.id, d.numero) })
                                if (d.estado == "solicitado") add("⚡ Generar" to { generarDoc(d.id, layout) })
                                if (d.estado != "anulado") add("Anular" to { anularDoc(d.id, layout) })
                                add("Eliminar" to { eliminarDoc(d.id, layout) })
                            }
                        ))
                    }
                } else {
                    tvEmpty.text = "No hay documentos"
                    layout.addView(tvEmpty)
                }
            } catch (e: Exception) {
                tvEmpty.text = "Error: ${e.message}"
            }
        }
    }

    private fun downloadPdf(id: Int, numero: String?) {
        lifecycleScope.launch {
            try {
                val resp = Api.svc().docsPdf(token, id)
                if (resp.isSuccessful) {
                    val bytes = resp.body()?.bytes() ?: return@launch
                    val file = File(getExternalFilesDir(null), "${numero ?: "doc"}.pdf")
                    FileOutputStream(file).use { it.write(bytes) }
                    Toast.makeText(this@MainActivity, "PDF guardado: ${file.name}", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@MainActivity, "Error al descargar PDF", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun eliminarDoc(id: Int, layout: LinearLayout) {
        AlertDialog.Builder(this)
            .setTitle("Eliminar documento")
            .setMessage("¿Eliminar este documento permanentemente?")
            .setPositiveButton("Eliminar") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = Api.svc().docsDelete(token, id)
                        Toast.makeText(this@MainActivity, if (resp.ok) "Eliminado" else (resp.error ?: "Error"), Toast.LENGTH_SHORT).show()
                        if (resp.ok) loadDocs()
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    // ==================== MÁS ====================
    private fun loadMas() {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(16, 16, 16, 16) }

        // Config
        val tvConfigTitle = TextView(this).apply { text = "Configuración"; textSize = 18f; setPadding(0, 0, 0, 16) }
        layout.addView(tvConfigTitle)

        val tvConfig = TextView(this).apply { text = "Cargando config..." }
        layout.addView(tvConfig)

        // Password
        val tvPwTitle = TextView(this).apply { text = "Cambiar contraseña"; textSize = 18f; setPadding(0, 32, 0, 16) }
        layout.addView(tvPwTitle)

        val etOldPass = EditText(this).apply { hint = "Contraseña actual" }
        val etNewPass = EditText(this).apply { hint = "Nueva contraseña"; inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD }
        layout.addView(etOldPass)
        layout.addView(etNewPass)

        val btnPw = Button(this).apply { text = "Cambiar contraseña" }
        layout.addView(btnPw)

        // Logout
        val btnLogout = Button(this).apply {
            text = "Cerrar sesión"
            setTextColor(0xFFEF4444.toInt())
            setBackgroundColor(0xFFFEE2E2.toInt())
        }
        layout.addView(btnLogout)

        scroll.addView(layout)
        container.addView(scroll)

        // Load config
        lifecycleScope.launch {
            try {
                val resp = Api.svc().configGet(token)
                if (resp.ok && resp.config.isNotEmpty()) {
                    val c = resp.config
                    tvConfig.text = """
                        Precio plan: ${c["precio_plan"]} CUP
                        Docs plan: ${c["docs_plan"]}
                        Días plan: ${c["dias_plan"]}
                        Precio extra: ${c["precio_extra"]} CUP
                        Docs extra: ${c["docs_extra"]}
                        Días gracia: ${c["dias_gracia"]}
                        Autogenerar: ${if (c["autogenerar"] == "1") "Sí" else "No"}
                    """.trimIndent()
                }
            } catch (e: Exception) {
                tvConfig.text = "Error: ${e.message}"
            }
        }

        btnPw.setOnClickListener {
            val old = etOldPass.text.toString().trim()
            val new = etNewPass.text.toString().trim()
            if (old.isEmpty() || new.isEmpty()) {
                Toast.makeText(this, "Complete ambos campos", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            lifecycleScope.launch {
                try {
                    val resp = Api.svc().password(token, mapOf("username" to "admin", "old" to old, "new" to new))
                    Toast.makeText(this@MainActivity, resp.mensaje ?: resp.error ?: "Listo", Toast.LENGTH_SHORT).show()
                    if (resp.ok) {
                        etOldPass.setText("")
                        etNewPass.setText("")
                    }
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }

        btnLogout.setOnClickListener {
            Sesion.borrar(this@MainActivity)
            startActivity(Intent(this@MainActivity, LoginActivity::class.java))
            finish()
        }
    }

    // ==================== UTILIDADES ====================
    private fun createCard(title: String, subtitle: String, actions: List<Pair<String, () -> Unit>>): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 20, 24, 20)
            setBackgroundColor(0xFFFFFFFF.toInt())
            val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            params.setMargins(0, 0, 0, 16)
            layoutParams = params
        }

        val tvTitle = TextView(this).apply {
            text = title
            textSize = 15f
            setTextColor(0xFF0f172a.toInt())
            setTypeface(null, android.graphics.Typeface.BOLD)
        }
        card.addView(tvTitle)

        if (subtitle.isNotEmpty()) {
            val tvSub = TextView(this).apply {
                text = subtitle
                textSize = 12f
                setTextColor(0xFF64748b.toInt())
                setPadding(0, 8, 0, if (actions.isNotEmpty()) 12 else 0)
            }
            card.addView(tvSub)
        }

        if (actions.isNotEmpty()) {
            val btnRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for ((label, action) in actions) {
                val isDelete = label.contains("Eliminar")
                val btn = Button(this).apply {
                    text = label
                    textSize = 11f
                    setBackgroundColor(if (isDelete) 0xFFFEE2E2.toInt() else 0xFFE0F2F1.toInt())
            setTextColor(if (isDelete) 0xFF991B1B.toInt() else 0xFF0d9488.toInt())
                    val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
                    params.setMargins(0, 0, 8, 0)
                    layoutParams = params
                    setPadding(24, 8, 24, 8)
                    setOnClickListener { action() }
                }
                btnRow.addView(btn)
            }
            card.addView(btnRow)
        }

        return card
    }
}

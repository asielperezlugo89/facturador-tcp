package com.tcpfacturador.cliente

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.FileProvider
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

class DocumentosFragment : Fragment() {

    private lateinit var rvDocs: RecyclerView
    private lateinit var emptyState: View
    private lateinit var tvDocCount: TextView
    private lateinit var etSearch: TextInputEditText
    private var allDocs = listOf<DocInfo>()

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? =
        inflater.inflate(R.layout.fragment_documentos, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        rvDocs = view.findViewById(R.id.rvDocs)
        emptyState = view.findViewById(R.id.emptyState)
        tvDocCount = view.findViewById(R.id.tvDocCount)
        etSearch = view.findViewById(R.id.etSearch)

        rvDocs.layoutManager = LinearLayoutManager(context)

        etSearch.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                filterDocs(s.toString())
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })

        (activity as? MainActivity)?.updateToolbarTitle("Mis Documentos", "Consulta de documentos")
        loadDocs()
    }

    private fun loadDocs() {
        val ctx = context ?: return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val token = Sesion.token(ctx)
                val device = Sesion.deviceId(ctx)
                val resp = Api.svc().misDocumentos(token, device)
                withContext(Dispatchers.Main) {
                    allDocs = resp.documentos
                    tvDocCount.text = "${allDocs.size} documentos"
                    renderDocs(allDocs)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun filterDocs(query: String) {
        val q = query.lowercase()
        val filtered = allDocs.filter {
            it.numero?.lowercase()?.contains(q) == true ||
            it.empresa?.lowercase()?.contains(q) == true ||
            it.tipo.lowercase().contains(q) ||
            it.estado.lowercase().contains(q)
        }
        renderDocs(filtered)
    }

    private fun renderDocs(docs: List<DocInfo>) {
        if (docs.isEmpty()) {
            rvDocs.visibility = View.GONE
            emptyState.visibility = View.VISIBLE
        } else {
            rvDocs.visibility = View.VISIBLE
            emptyState.visibility = View.GONE
            rvDocs.adapter = DocAdapter(docs) { doc -> downloadPdf(doc) }
        }
    }

    private fun downloadPdf(doc: DocInfo) {
        if (!doc.pdf) {
            Toast.makeText(context, "PDF no disponible", Toast.LENGTH_SHORT).show()
            return
        }
        val ctx = context ?: return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val token = Sesion.token(ctx)
                val device = Sesion.deviceId(ctx)
                val resp = Api.svc().pdf(token, device, doc.id)
                if (resp.isSuccessful) {
                    val body = resp.body() ?: return@launch
                    val dir = File(ctx.cacheDir, "pdfs").apply { mkdirs() }
                    val file = File(dir, "doc_${doc.id}.pdf")
                    file.outputStream().use { out -> body.byteStream().copyTo(out) }
                    withContext(Dispatchers.Main) {
                        openPdf(file)
                    }
                } else {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(context, "Error al descargar PDF", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun openPdf(file: File) {
        val ctx = context ?: return
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/pdf")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(ctx, "No hay visor de PDF instalado", Toast.LENGTH_SHORT).show()
        }
    }
}

class DocAdapter(
    private val items: List<DocInfo>,
    private val onPdfClick: (DocInfo) -> Unit
) : RecyclerView.Adapter<DocAdapter.VH>() {

    inner class VH(v: View) : RecyclerView.ViewHolder(v) {
        val tvDocId: TextView = v.findViewById(R.id.tvDocId)
        val tvClient: TextView = v.findViewById(R.id.tvClient)
        val tvType: TextView = v.findViewById(R.id.tvType)
        val tvAmount: TextView = v.findViewById(R.id.tvAmount)
        val tvDate: TextView = v.findViewById(R.id.tvDate)
        val tvStatus: TextView = v.findViewById(R.id.tvStatus)
        val btnPdf: View = v.findViewById(R.id.btnPdf)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context).inflate(R.layout.item_documento, parent, false)
        return VH(v)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val doc = items[position]
        holder.tvDocId.text = doc.numero ?: "DOC-${doc.id}"
        holder.tvClient.text = doc.empresa ?: "—"
        holder.tvType.text = "📄 ${doc.tipo}"
        holder.tvAmount.text = doc.total_txt.ifEmpty { "$${doc.total}" }
        holder.tvDate.text = doc.fecha ?: "—"
        holder.tvStatus.text = doc.estado

        val (pillBg, pillColor) = when (doc.estado.lowercase()) {
            "activo", "emitido" -> R.drawable.pill_green to R.color.green_text
            "pendiente", "procesando" -> R.drawable.pill_amber to R.color.amber_text
            "anulado", "rechazado" -> R.drawable.pill_red to R.color.red_text
            else -> R.drawable.pill_blue to R.color.blue_text
        }
        holder.tvStatus.setBackgroundResource(pillBg)
        holder.tvStatus.setTextColor(holder.itemView.context.getColor(pillColor))

        holder.btnPdf.visibility = if (doc.pdf) View.VISIBLE else View.GONE
        holder.btnPdf.setOnClickListener { onPdfClick(doc) }
    }

    override fun getItemCount() = items.size
}

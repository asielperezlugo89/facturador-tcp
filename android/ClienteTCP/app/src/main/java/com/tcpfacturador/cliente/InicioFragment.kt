package com.tcpfacturador.cliente

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.google.android.material.card.MaterialCardView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class InicioFragment : Fragment() {

    private lateinit var tvClientName: TextView
    private lateinit var tvClientPhone: TextView
    private lateinit var tvStatus: TextView
    private lateinit var tvStatusPill: TextView
    private lateinit var tvDocCount: TextView
    private lateinit var tvAvisoCount: TextView
    private lateinit var recentDocsContainer: LinearLayout
    private lateinit var tvNoDocs: TextView

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? =
        inflater.inflate(R.layout.fragment_inicio, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        tvClientName = view.findViewById(R.id.tvClientName)
        tvClientPhone = view.findViewById(R.id.tvClientPhone)
        tvStatus = view.findViewById(R.id.tvStatus)
        tvStatusPill = view.findViewById(R.id.tvStatusPill)
        tvDocCount = view.findViewById(R.id.tvDocCount)
        tvAvisoCount = view.findViewById(R.id.tvAvisoCount)
        recentDocsContainer = view.findViewById(R.id.recentDocsContainer)
        tvNoDocs = view.findViewById(R.id.tvNoDocs)

        (activity as? MainActivity)?.updateToolbarTitle("Inicio", "Facturador TCP")
        loadData()
    }

    private fun loadData() {
        val ctx = context ?: return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val token = Sesion.token(ctx)
                val device = Sesion.deviceId(ctx)

                val estadoResp = Api.svc().estado(token, device)
                val docsResp = Api.svc().misDocumentos(token, device)
                val avisosResp = Api.svc().avisos(token, device)

                withContext(Dispatchers.Main) {
                    if (estadoResp.ok) {
                        tvClientName.text = "Código: ${estadoResp.codigo ?: "—"}"
                        tvStatus.text = estadoResp.estado ?: "Desconocido"
                        val (label, bgRes) = when (estadoResp.estado?.lowercase()) {
                            "activo" -> "Activo" to R.drawable.pill_green
                            "inactivo", "suspendido" -> "Inactivo" to R.drawable.pill_red
                            "pendiente" -> "Pendiente" to R.drawable.pill_amber
                            else -> (estadoResp.estado ?: "—") to R.drawable.pill_blue
                        }
                        tvStatusPill.text = label
                        tvStatusPill.setBackgroundResource(bgRes)
                    }

                    val docs = docsResp.documentos
                    tvDocCount.text = docs.size.toString()
                    tvAvisoCount.text = avisosResp.notificaciones.size.toString()

                    recentDocsContainer.removeAllViews()
                    if (docs.isEmpty()) {
                        tvNoDocs.visibility = View.VISIBLE
                    } else {
                        tvNoDocs.visibility = View.GONE
                        docs.take(3).forEach { doc ->
                            val card = LayoutInflater.from(context)
                                .inflate(R.layout.item_documento, recentDocsContainer, false)
                            card.findViewById<TextView>(R.id.tvDocId).text = doc.numero ?: "DOC-${doc.id}"
                            card.findViewById<TextView>(R.id.tvClient).text = doc.empresa ?: "—"
                            card.findViewById<TextView>(R.id.tvType).text = "📄 ${doc.tipo}"
                            card.findViewById<TextView>(R.id.tvAmount).text = doc.total_txt.ifEmpty { "$${doc.total}" }
                            card.findViewById<TextView>(R.id.tvDate).text = doc.fecha ?: "—"
                            card.findViewById<TextView>(R.id.tvStatus).text = doc.estado
                            card.findViewById<MaterialCardView>(R.id.btnPdf).visibility =
                                if (doc.pdf) View.VISIBLE else View.GONE
                            recentDocsContainer.addView(card)
                        }
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
}

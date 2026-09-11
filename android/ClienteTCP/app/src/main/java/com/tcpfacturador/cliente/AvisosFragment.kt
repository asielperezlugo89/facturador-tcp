package com.tcpfacturador.cliente

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class AvisosFragment : Fragment() {

    private lateinit var rvAvisos: RecyclerView
    private lateinit var emptyState: View

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? =
        inflater.inflate(R.layout.fragment_avisos, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        rvAvisos = view.findViewById(R.id.rvAvisos)
        emptyState = view.findViewById(R.id.emptyState)
        rvAvisos.layoutManager = LinearLayoutManager(context)

        (activity as? MainActivity)?.updateToolbarTitle("Notificaciones", "Avisos del sistema")
        loadAvisos()
    }

    private fun loadAvisos() {
        val ctx = context ?: return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val token = Sesion.token(ctx)
                val device = Sesion.deviceId(ctx)
                val resp = Api.svc().avisos(token, device)
                withContext(Dispatchers.Main) {
                    val avisos = resp.notificaciones
                    if (avisos.isEmpty()) {
                        rvAvisos.visibility = View.GONE
                        emptyState.visibility = View.VISIBLE
                    } else {
                        rvAvisos.visibility = View.VISIBLE
                        emptyState.visibility = View.GONE
                        rvAvisos.adapter = AvisoAdapter(avisos)
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

class AvisoAdapter(private val items: List<Aviso>) : RecyclerView.Adapter<AvisoAdapter.VH>() {

    inner class VH(v: View) : RecyclerView.ViewHolder(v) {
        val tvIcon: TextView = v.findViewById(R.id.tvIcon)
        val tvTitle: TextView = v.findViewById(R.id.tvTitle)
        val tvMessage: TextView = v.findViewById(R.id.tvMessage)
        val tvDate: TextView = v.findViewById(R.id.tvDate)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context).inflate(R.layout.item_aviso, parent, false)
        return VH(v)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val a = items[position]
        holder.tvIcon.text = when (a.tipo?.lowercase()) {
            "documento" -> "📄"
            "pago" -> "💰"
            "sistema" -> "⚙️"
            "alerta" -> "⚠️"
            else -> "🔔"
        }
        holder.tvTitle.text = a.titulo
        holder.tvMessage.text = a.mensaje
        holder.tvDate.text = a.created_at
    }

    override fun getItemCount() = items.size
}

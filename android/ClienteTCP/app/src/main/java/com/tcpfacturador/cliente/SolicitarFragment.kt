package com.tcpfacturador.cliente

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.ProgressBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SolicitarFragment : Fragment() {

    private lateinit var etDocId: TextInputEditText
    private lateinit var spinnerType: Spinner
    private lateinit var etClient: TextInputEditText
    private lateinit var etCedula: TextInputEditText
    private lateinit var etAddress: TextInputEditText
    private lateinit var etPhone: TextInputEditText
    private lateinit var etAmount: TextInputEditText
    private lateinit var etNotes: TextInputEditText
    private lateinit var tvError: TextView
    private lateinit var btnSubmit: MaterialButton
    private lateinit var progressBar: ProgressBar

    private val docTypes = arrayOf("Factura", "Nota de Venta", "Contrato", "Comprobante", "Otro")

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? =
        inflater.inflate(R.layout.fragment_solicitar, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        etDocId = view.findViewById(R.id.etDocId)
        spinnerType = view.findViewById(R.id.spinnerType)
        etClient = view.findViewById(R.id.etClient)
        etCedula = view.findViewById(R.id.etCedula)
        etAddress = view.findViewById(R.id.etAddress)
        etPhone = view.findViewById(R.id.etPhone)
        etAmount = view.findViewById(R.id.etAmount)
        etNotes = view.findViewById(R.id.etNotes)
        tvError = view.findViewById(R.id.tvError)
        btnSubmit = view.findViewById(R.id.btnSubmit)
        progressBar = view.findViewById(R.id.progressBar)

        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_item, docTypes)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerType.adapter = adapter

        btnSubmit.setOnClickListener { submit() }
        (activity as? MainActivity)?.updateToolbarTitle("Solicitar Documento", "Nuevo registro")
    }

    private fun submit() {
        val docId = etDocId.text.toString().trim()
        val client = etClient.text.toString().trim()
        val cedula = etCedula.text.toString().trim()
        val address = etAddress.text.toString().trim()
        val phone = etPhone.text.toString().trim()
        val amount = etAmount.text.toString().trim()
        val notes = etNotes.text.toString().trim()

        if (docId.isEmpty() || client.isEmpty() || cedula.isEmpty()) {
            tvError.text = "Complete No. Documento, Nombre y Cédula"
            tvError.visibility = View.VISIBLE
            return
        }

        tvError.visibility = View.GONE
        btnSubmit.isEnabled = false
        progressBar.visibility = View.VISIBLE

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val ctx = context ?: return@launch
                val token = Sesion.token(ctx)
                val device = Sesion.deviceId(ctx)
                val tipo = docTypes[spinnerType.selectedItemPosition]
                val amountVal = amount.toDoubleOrNull() ?: 0.0

                val items = listOf(
                    ItemDoc(descripcion = "Documento $tipo", cantidad = 1.0, precio = amountVal)
                )
                val req = ReqDoc(
                    tipo = tipo,
                    contrato_no = docId,
                    items = items
                )
                val resp = Api.svc().solicitar(token, device, req)

                withContext(Dispatchers.Main) {
                    if (resp.ok) {
                        Toast.makeText(context, "Documento ${resp.doc_id} registrado", Toast.LENGTH_SHORT).show()
                        clearForm()
                    } else {
                        tvError.text = resp.error ?: resp.mensaje ?: "Error desconocido"
                        tvError.visibility = View.VISIBLE
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    tvError.text = "Error de conexión: ${e.message}"
                    tvError.visibility = View.VISIBLE
                }
            } finally {
                withContext(Dispatchers.Main) {
                    btnSubmit.isEnabled = true
                    progressBar.visibility = View.GONE
                }
            }
        }
    }

    private fun clearForm() {
        etDocId.text?.clear()
        etClient.text?.clear()
        etCedula.text?.clear()
        etAddress.text?.clear()
        etPhone.text?.clear()
        etAmount.text?.clear()
        etNotes.text?.clear()
        spinnerType.setSelection(0)
    }
}

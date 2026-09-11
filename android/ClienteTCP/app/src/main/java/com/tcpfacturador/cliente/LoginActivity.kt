package com.tcpfacturador.cliente

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class LoginActivity : AppCompatActivity() {

    private lateinit var tilPhone: TextInputLayout
    private lateinit var etPhone: TextInputEditText
    private lateinit var tvError: TextView
    private lateinit var btnConnect: MaterialButton
    private lateinit var progressBar: ProgressBar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Check if already logged in
        val token = Sesion.token(this)
        if (token.isNotEmpty()) {
            goMain()
            return
        }

        setContentView(R.layout.activity_login)

        tilPhone = findViewById(R.id.tilPhone)
        etPhone = findViewById(R.id.etPhone)
        tvError = findViewById(R.id.tvError)
        btnConnect = findViewById(R.id.btnConnect)
        progressBar = findViewById(R.id.progressBar)

        btnConnect.setOnClickListener { doLogin() }
    }

    private fun doLogin() {
        val phone = etPhone.text.toString().trim()
        if (phone.isEmpty()) {
            tilPhone.error = getString(R.string.login_error_empty)
            return
        }
        tilPhone.error = null
        tvError.visibility = View.GONE
        setLoading(true)

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val deviceId = Sesion.deviceId(this@LoginActivity)
                val body = mapOf("telefono" to phone, "nombre_apellidos" to phone, "device_id" to deviceId)
                val resp = Api.svc().registro(body)
                withContext(Dispatchers.Main) {
                    if (resp.ok && resp.token != null) {
                        Sesion.guardarToken(this@LoginActivity, resp.token)
                        goMain()
                    } else {
                        showError(resp.error ?: resp.mensaje ?: getString(R.string.login_error_device))
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    showError(getString(R.string.login_error_server) + "\n${e.localizedMessage}")
                }
            }
        }
    }

    private fun goMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    private fun showError(msg: String) {
        setLoading(false)
        tvError.text = msg
        tvError.visibility = View.VISIBLE
    }

    private fun setLoading(loading: Boolean) {
        btnConnect.isEnabled = !loading
        progressBar.visibility = if (loading) View.VISIBLE else View.GONE
        btnConnect.text = if (loading) "" else getString(R.string.login_btn)
    }
}

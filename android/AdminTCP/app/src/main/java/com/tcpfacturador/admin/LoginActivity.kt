package com.tcpfacturador.admin

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val token = Sesion.token(this)
        if (token.isNotEmpty()) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }

        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(64, 64, 64, 64)
            gravity = android.view.Gravity.CENTER
        }

        val tvTitle = android.widget.TextView(this).apply {
            text = "TCP Admin"
            textSize = 28f
            gravity = android.view.Gravity.CENTER
            setPadding(0, 0, 0, 48)
        }
        layout.addView(tvTitle)

        val etUser = EditText(this).apply {
            hint = "Usuario"
            setText("admin")
        }
        layout.addView(etUser)

        val etPass = EditText(this).apply {
            hint = "Contraseña"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            setText("admin123")
        }
        layout.addView(etPass)

        val btnLogin = Button(this).apply { text = "Iniciar sesión" }
        layout.addView(btnLogin)

        setContentView(layout)

        btnLogin.setOnClickListener {
            val user = etUser.text.toString().trim()
            val pass = etPass.text.toString().trim()
            if (user.isEmpty() || pass.isEmpty()) {
                Toast.makeText(this, "Complete todos los campos", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            btnLogin.isEnabled = false
            btnLogin.text = "Entrando..."
            lifecycleScope.launch {
                try {
                    val resp = Api.svc().login(mapOf("username" to user, "password" to pass))
                    if (resp.ok && resp.token != null) {
                        Sesion.guardarToken(this@LoginActivity, resp.token)
                        startActivity(Intent(this@LoginActivity, MainActivity::class.java))
                        finish()
                    } else {
                        Toast.makeText(this@LoginActivity, resp.error ?: "Error", Toast.LENGTH_SHORT).show()
                    }
                } catch (e: Exception) {
                    Toast.makeText(this@LoginActivity, "Error de red: ${e.message}", Toast.LENGTH_SHORT).show()
                } finally {
                    btnLogin.isEnabled = true
                    btnLogin.text = "Iniciar sesión"
                }
            }
        }
    }
}

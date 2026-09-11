package com.tcpfacturador.admin

import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
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

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFFF1F5F9.toInt())
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT)
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(64, 80, 64, 64)
            gravity = Gravity.CENTER_HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT)
        }

        // Logo circle
        val logoContainer = LinearLayout(this).apply {
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            setPadding(0, 0, 0, 24)
        }
        val logoTv = TextView(this).apply {
            text = "\uD83D\uDCCB"
            textSize = 40f
            gravity = Gravity.CENTER
            setPadding(0, 24, 0, 0)
        }
        logoContainer.addView(logoTv)
        layout.addView(logoContainer)

        val tvTitle = TextView(this).apply {
            text = "TCP Admin"
            textSize = 28f
            gravity = Gravity.CENTER
            setTextColor(0xFF0d9488.toInt())
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        layout.addView(tvTitle)

        val tvSubtitle = TextView(this).apply {
            text = "Panel de Administración"
            textSize = 14f
            gravity = Gravity.CENTER
            setTextColor(0xFF64748b.toInt())
            setPadding(0, 0, 0, 40)
        }
        layout.addView(tvSubtitle)

        val etUser = EditText(this).apply {
            hint = "Usuario"
            setText("admin")
            setPadding(24, 16, 24, 16)
        }
        layout.addView(etUser)

        val etPass = EditText(this).apply {
            hint = "Contraseña"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            setText("admin123")
            setPadding(24, 16, 24, 16)
        }
        layout.addView(etPass)

        val tvError = TextView(this).apply {
            setPadding(0, 8, 0, 0)
            setTextColor(0xFFEF4444.toInt())
            textSize = 13f
            visibility = android.view.View.GONE
        }
        layout.addView(tvError)

        val btnLogin = Button(this).apply {
            text = "Iniciar sesión"
            setTextColor(0xFFFFFFFF.toInt())
            setBackgroundColor(0xFF0d9488.toInt())
            setPadding(24, 14, 24, 14)
            val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            params.setMargins(0, 16, 0, 0)
            layoutParams = params
        }
        layout.addView(btnLogin)

        val tvVersion = TextView(this).apply {
            text = "v1.0 · Facturador TCP"
            textSize = 12f
            gravity = Gravity.CENTER
            setTextColor(0xFF94a3b8.toInt())
            setPadding(0, 40, 0, 0)
        }
        layout.addView(tvVersion)

        root.addView(layout)
        setContentView(root)

        btnLogin.setOnClickListener {
            val user = etUser.text.toString().trim()
            val pass = etPass.text.toString().trim()
            if (user.isEmpty() || pass.isEmpty()) {
                tvError.text = "Complete todos los campos"
                tvError.visibility = android.view.View.VISIBLE
                return@setOnClickListener
            }
            tvError.visibility = android.view.View.GONE
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
                        tvError.text = resp.error ?: "Credenciales incorrectas"
                        tvError.visibility = android.view.View.VISIBLE
                    }
                } catch (e: Exception) {
                    tvError.text = "Error de red: ${e.message}"
                    tvError.visibility = android.view.View.VISIBLE
                } finally {
                    btnLogin.isEnabled = true
                    btnLogin.text = "Iniciar sesión"
                }
            }
        }
    }
}

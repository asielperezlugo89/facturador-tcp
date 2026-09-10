package com.tcpfacturador.cliente

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val tv = TextView(this).apply {
            text = "TCP Cliente - Conectando al servidor..."
            textSize = 18f
            setPadding(48, 48, 48, 48)
        }
        setContentView(tv)
    }
}

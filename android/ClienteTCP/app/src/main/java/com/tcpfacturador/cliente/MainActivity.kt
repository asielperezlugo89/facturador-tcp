package com.tcpfacturador.cliente

import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.bottomnavigation.BottomNavigationView

class MainActivity : AppCompatActivity() {

    private lateinit var toolbar: MaterialToolbar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        toolbar = findViewById(R.id.toolbar)
        setSupportActionBar(toolbar)

        val bottomNav = findViewById<BottomNavigationView>(R.id.bottomNav)
        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_inicio -> { loadFragment(InicioFragment()); true }
                R.id.nav_solicitar -> { loadFragment(SolicitarFragment()); true }
                R.id.nav_documentos -> { loadFragment(DocumentosFragment()); true }
                R.id.nav_avisos -> { loadFragment(AvisosFragment()); true }
                else -> false
            }
        }

        if (savedInstanceState == null) {
            bottomNav.selectedItemId = R.id.nav_inicio
        }
    }

    private fun loadFragment(f: Fragment) {
        supportFragmentManager.beginTransaction()
            .replace(R.id.fragmentContainer, f)
            .commit()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_toolbar, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == R.id.action_logout) {
            AlertDialog.Builder(this)
                .setMessage(getString(R.string.confirm_logout))
                .setPositiveButton(getString(R.string.yes)) { _, _ ->
                    Sesion.borrar(this)
                    startActivity(Intent(this, LoginActivity::class.java))
                    finish()
                }
                .setNegativeButton(getString(R.string.no), null)
                .show()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    fun updateToolbarTitle(title: String, subtitle: String = "") {
        toolbar.title = title
        toolbar.subtitle = subtitle
    }
}

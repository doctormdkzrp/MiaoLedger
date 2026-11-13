package com.miaoledger

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.miaoledger.data.Api
import com.miaoledger.data.LocalDb
import com.miaoledger.data.Prefs
import com.miaoledger.ui.AppRoot
import com.miaoledger.ui.MiaoTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val prefs = Prefs(applicationContext)
        val db = LocalDb(applicationContext)
        val api = Api(prefs)

        setContent {
            MiaoTheme {
                AppRoot(prefs = prefs, db = db, api = api)
            }
        }
    }
}

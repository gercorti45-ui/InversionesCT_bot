#!/usr/bin/env python3
# InversionesCT_full.py
# Bot completo InversionesCT - todo integrado: OCR opcional, referidos, inversiones,
# actualización de datos por campo, panel admin, verificación DB y reconexión 24/7.

import os
import time
import sqlite3
import datetime
import traceback
import re
from telebot import TeleBot, types

# ---------------- OCR (opcional) ----------------
TESSERACT_AVAILABLE = False
try:
    from PIL import Image
    import pytesseract
    # Si usas Pydroid y la ruta es diferente, ajusta esta línea:
    # pytesseract.pytesseract.tesseract_cmd = "/data/data/ru.iiec.pydroid3/files/usr/bin/tesseract"
    TESSERACT_AVAILABLE = True
except Exception:
    TESSERACT_AVAILABLE = False

# ---------------- CONFIG ----------------
TOKEN = "8362936227:AAHlr3AY5iUDdIk8oFoK63wxT6bsgrYYfDk"
BOT_USERNAME = "InversionesCT_bot"
ADMIN_ID = 5871502663
NEQUI_DESTINO = "3053706109"
DB_FILE = "inversionesct.db"
DOWNLOAD_DIR = "comprobantes"

bot = TeleBot(TOKEN)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ---------------- DB helpers ----------------
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        user_id INTEGER PRIMARY KEY,
        nombre TEXT,
        telefono TEXT,
        nequi TEXT,
        cedula TEXT,
        referido_por INTEGER,
        referidos INTEGER DEFAULT 0,
        total_invertido INTEGER DEFAULT 0,
        ganancia_total INTEGER DEFAULT 0
    );
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS inversiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        monto INTEGER,
        fecha_inversion TEXT,
        fecha_pago TEXT,
        estado TEXT,
        comprobante_path TEXT,
        ocr_text TEXT
    );
    ''')
    conn.commit()
    conn.close()

def verificar_columnas():
    """Agrega columnas faltantes sin borrar datos."""
    columnas_necesarias = {
        "usuarios": {
            "nombre": "TEXT",
            "telefono": "TEXT",
            "nequi": "TEXT",
            "cedula": "TEXT",
            "referido_por": "INTEGER",
            "referidos": "INTEGER DEFAULT 0",
            "total_invertido": "INTEGER DEFAULT 0",
            "ganancia_total": "INTEGER DEFAULT 0"
        },
        "inversiones": {
            "user_id": "INTEGER",
            "monto": "INTEGER",
            "fecha_inversion": "TEXT",
            "fecha_pago": "TEXT",
            "estado": "TEXT",
            "comprobante_path": "TEXT",
            "ocr_text": "TEXT"
        }
    }
    conn = get_conn()
    cur = conn.cursor()
    for tabla, cols in columnas_necesarias.items():
        try:
            cur.execute(f"PRAGMA table_info({tabla})")
            existentes = [c[1] for c in cur.fetchall()]
            for nombre, tipo in cols.items():
                if nombre not in existentes:
                    try:
                        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")
                        print(f"🧩 Columna agregada automáticamente: {tabla}.{nombre}")
                    except Exception as e:
                        print(f"⚠️ Error agregando columna {tabla}.{nombre}: {e}")
        except Exception as e:
            print(f"⚠️ verificar_columnas fallo para tabla {tabla}: {e}")
    conn.commit()
    conn.close()

# Inicializar y verificar DB
init_db()
verificar_columnas()

# ---------------- Utilities ----------------
def fmt_money(n):
    try:
        return f"{int(n):,}".replace(",", ".")
    except:
        return str(n)

def safe_send(chat_id, text, **kwargs):
    """Envía mensaje con manejo de errores en parse_mode."""
    try:
        bot.send_message(chat_id, text, **kwargs)
    except Exception:
        try:
            bot.send_message(chat_id, text)
        except Exception:
            pass

# ---------------- Menus ----------------
def menu_principal_for(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("📈 Panel admin"), types.KeyboardButton("💰 Invertir"))
        markup.add(types.KeyboardButton("🤝 Referir amigos"), types.KeyboardButton("📊 Mi perfil"))
    else:
        markup.add(types.KeyboardButton("💰 Invertir"), types.KeyboardButton("🤝 Referir amigos"))
        markup.add(types.KeyboardButton("📊 Mi perfil"), types.KeyboardButton("👥 Mis referidos"))
    return markup

# ---------------- Start / Registro ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        parts = message.text.split()
        referido = None
        if len(parts) > 1:
            try:
                referido = int(parts[1])
            except:
                referido = None

        # mensaje de bienvenida (siempre)
        safe_send(chat_id,
            "💎 *Bienvenido a InversionesCT*\n\n"
            "Aquí puedes invertir, ganar y crecer junto a nuestra comunidad.\n"
            "Usa el menú para registrarte o explorar las opciones disponibles.",
            parse_mode="Markdown"
        )

        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT user_id FROM usuarios WHERE user_id=?", (user_id,))
        exists = cur.fetchone() is not None

        if not exists:
            cur.execute("INSERT OR IGNORE INTO usuarios (user_id, referido_por) VALUES (?, ?)", (user_id, referido))
            conn.commit()
            # si viene referido, incrementar conteo del referidor
            if referido and referido != user_id:
                try:
                    cur.execute("UPDATE usuarios SET referidos = referidos + 1 WHERE user_id=?", (referido,))
                    conn.commit()
                    try:
                        safe_send(referido, f"🎉 Nuevo usuario registrado gracias a tu enlace: ID {user_id}")
                    except:
                        pass
                except:
                    pass

        conn.close()

        if exists:
            safe_send(chat_id, "Selecciona una opción:", reply_markup=menu_principal_for(user_id))
        else:
            safe_send(chat_id, "Por favor escribe tu *nombre completo*:", parse_mode="Markdown")
            bot.register_next_step_handler_by_chat_id(chat_id, step_nombre)
    except Exception:
        traceback.print_exc()

def step_nombre(message):
    try:
        user_id = message.from_user.id
        nombre = message.text.strip()
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET nombre=? WHERE user_id=?", (nombre, user_id))
        conn.commit(); conn.close()
        safe_send(user_id, "📱 Ingresa tu número de teléfono:")
        bot.register_next_step_handler_by_chat_id(user_id, step_telefono)
    except Exception:
        traceback.print_exc()

def step_telefono(message):
    try:
        user_id = message.from_user.id
        telefono = message.text.strip()
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET telefono=? WHERE user_id=?", (telefono, user_id))
        conn.commit(); conn.close()
        safe_send(user_id, "🪪 Ingresa tu número de cédula:")
        bot.register_next_step_handler_by_chat_id(user_id, step_cedula)
    except Exception:
        traceback.print_exc()

def step_cedula(message):
    try:
        user_id = message.from_user.id
        cedula = message.text.strip()
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET cedula=? WHERE user_id=?", (cedula, user_id))
        conn.commit(); conn.close()
        safe_send(user_id, "💳 Ingresa tu número de Nequi:")
        bot.register_next_step_handler_by_chat_id(user_id, step_nequi)
    except Exception:
        traceback.print_exc()

def step_nequi(message):
    try:
        user_id = message.from_user.id
        nequi = message.text.strip()
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET nequi=? WHERE user_id=?", (nequi, user_id))
        conn.commit(); conn.close()
        safe_send(user_id, "✅ Registro completado. Aquí tienes el menú principal.", reply_markup=menu_principal_for(user_id))
    except Exception:
        traceback.print_exc()

# ---------------- Referidos ----------------
@bot.message_handler(func=lambda m: m.text == "🤝 Referir amigos")
def handler_referir(m):
    try:
        user_id = m.from_user.id
        referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        safe_send(user_id, "✨ Comparte tu enlace con tus amigos.")
        safe_send(user_id, f"🔗 Tu enlace personal:\n{referral_link}")
        safe_send(user_id, "Cada persona que se registre desde tu enlace quedará asociada a ti.")
    except Exception:
        traceback.print_exc()
        safe_send(m.from_user.id, "⚠️ No se pudo generar tu enlace en este momento. Intenta más tarde.")

# ---------------- Perfil & Actualización por campo ----------------
@bot.message_handler(func=lambda m: m.text == "📊 Mi perfil")
def handler_perfil(m):
    try:
        user_id = m.from_user.id
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT nombre, telefono, nequi, cedula, total_invertido, ganancia_total, referidos FROM usuarios WHERE user_id=?", (user_id,))
        r = cur.fetchone(); conn.close()
        if not r:
            safe_send(user_id, "⚠️ No estás registrado. Usa /start para registrarte.")
            return
        nombre, telefono, nequi, cedula, total_invertido, ganancia_total, referidos = r
        total_invertido = int(total_invertido or 0)
        ganancia_total = int(ganancia_total or 0)
        text = (
            f"👤 *Perfil:*\n"
            f"📛 Nombre: {nombre}\n"
            f"📱 Teléfono: {telefono}\n"
            f"💳 Nequi: {nequi}\n"
            f"🪪 Cédula: {cedula}\n"
            f"💰 Total invertido: ${fmt_money(total_invertido)}\n"
            f"💵 Ganancia acumulada: ${fmt_money(ganancia_total)}\n"
            f"🤝 Referidos: {referidos}"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Actualizar mis datos", callback_data="UPDATE_MENU"))
        safe_send(user_id, text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        traceback.print_exc()

@bot.callback_query_handler(func=lambda c: c.data == "UPDATE_MENU")
def show_update_menu(c):
    try:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✏️ Nombre", callback_data="UPD|nombre"),
            types.InlineKeyboardButton("📱 Teléfono", callback_data="UPD|telefono"),
            types.InlineKeyboardButton("🪪 Cédula", callback_data="UPD|cedula"),
            types.InlineKeyboardButton("💳 Nequi", callback_data="UPD|nequi")
        )
        bot.send_message(c.message.chat.id, "Selecciona el dato que deseas actualizar:", reply_markup=markup)
    except Exception:
        traceback.print_exc()

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("UPD|"))
def actualizar_dato_callback(c):
    try:
        campo = c.data.split("|")[1]
        friendly = {"nombre":"nombre", "telefono":"teléfono", "cedula":"cédula", "nequi":"Nequi"}
        display = friendly.get(campo, campo)
        bot.send_message(c.message.chat.id, f"Escribe el nuevo valor para *{display}*:", parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(c.message.chat.id, lambda m: guardar_actualizacion(m, campo))
    except Exception:
        traceback.print_exc()

def guardar_actualizacion(message, campo):
    try:
        user_id = message.from_user.id
        nuevo = message.text.strip()
        conn = get_conn(); cur = conn.cursor()
        # proteger contra inyección: campo debe ser uno de los permitidos
        if campo not in ("nombre", "telefono", "cedula", "nequi"):
            safe_send(user_id, "⚠️ Campo no válido.")
            conn.close()
            return
        cur.execute(f"UPDATE usuarios SET {campo}=? WHERE user_id=?", (nuevo, user_id))
        conn.commit(); conn.close()
        safe_send(user_id, f"✅ Tu {campo} ha sido actualizado correctamente.", reply_markup=menu_principal_for(user_id))
    except Exception:
        traceback.print_exc()
        safe_send(message.chat.id, "⚠️ No se pudo actualizar tu dato. Intenta de nuevo.")

# ---------------- Mis referidos ----------------
@bot.message_handler(func=lambda m: m.text == "👥 Mis referidos")
def handler_mis_referidos(m):
    try:
        user_id = m.from_user.id
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT referidos FROM usuarios WHERE user_id=?", (user_id,))
        r = cur.fetchone(); conn.close()
        referidos = r[0] if r else 0
        safe_send(user_id, f"👥 Has referido a {referidos} persona(s).")
    except Exception:
        traceback.print_exc()

# ---------------- Inversiones (regla: 1ra inversión libre, después necesita referido) ----------------
INV_OPTIONS = [100000, 300000, 500000]

@bot.message_handler(func=lambda m: m.text == "💰 Invertir")
def handler_invertir(m):
    try:
        user_id = m.from_user.id
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM inversiones WHERE user_id=?", (user_id,))
        total_inversiones = cur.fetchone()[0] or 0
        cur.execute("SELECT referidos FROM usuarios WHERE user_id=?", (user_id,))
        r = cur.fetchone()
        referidos = r[0] if r and r[0] is not None else 0
        conn.close()

        if total_inversiones >= 1 and referidos < 1:
            safe_send(
                m.chat.id,
                "⚠️ Para realizar una nueva inversión debes invitar al menos a 1 amigo usando tu enlace de referido.\n\n"
                "Comparte tu enlace desde la opción 🤝 Referir amigos en el menú principal."
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=3)
        for amt in INV_OPTIONS:
            markup.add(types.InlineKeyboardButton(f"💵 {fmt_money(amt)}", callback_data=f"INV|{amt}"))
        safe_send(m.chat.id, "Selecciona el monto a invertir:", reply_markup=markup)
    except Exception:
        traceback.print_exc()

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("INV|"))
def callback_inv(c):
    try:
        monto = int(c.data.split("|")[1])
        uid = c.from_user.id
        safe_send(uid, f"📸 Envía la imagen del comprobante Nequi por el valor de ${fmt_money(monto)} al número {NEQUI_DESTINO}.")
        bot.register_next_step_handler_by_chat_id(uid, lambda m: procesar_comprobante(m, monto))
        bot.answer_callback_query(c.id, "Enviar comprobante cuando estés listo.")
    except Exception:
        traceback.print_exc()

# ---------------- Guardado de archivo ----------------
def save_file_from_message(message, filename):
    try:
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document:
            file_id = message.document.file_id
        else:
            return None, "No hay archivo en el mensaje."
        file_info = bot.get_file(file_id)
        data = bot.download_file(file_info.file_path)
        path = os.path.join(DOWNLOAD_DIR, filename)
        with open(path, "wb") as f:
            f.write(data)
        return path, None
    except Exception as e:
        return None, str(e)

def extract_amount_from_text(text):
    # limpia no dígitos y toma el número más largo como candidato
    t = re.sub(r'[^\d]', ' ', text)
    nums = re.findall(r'\d{3,}', t)
    if not nums:
        return None
    candidate = max(nums, key=len)
    try:
        return int(candidate)
    except:
        return None

# ---------------- Procesar comprobante (OCR + registro) ----------------
def procesar_comprobante(message, monto):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        if not (message.photo or message.document):
            safe_send(chat_id, "⚠️ Debes enviar una imagen del comprobante.")
            return

        safe_send(chat_id, "🧾 Comprobante recibido. Verificando, esto puede tardar unos segundos ⏳...")
        timestamp = int(time.time())
        filename = f"comp_{user_id}_{timestamp}.jpg"
        saved_path, err = save_file_from_message(message, filename)
        if not saved_path:
            safe_send(chat_id, f"⚠️ Error al guardar archivo: {err}")
            return

        ocr_text = ""
        ocr_ok = False
        ocr_reason = ""
        monto_detected = None

        if TESSERACT_AVAILABLE:
            try:
                img = Image.open(saved_path)
                ocr_text = pytesseract.image_to_string(img, lang='spa')
                text_no_space = re.sub(r'\s+', '', ocr_text)
                monto_detected = extract_amount_from_text(ocr_text)
                if NEQUI_DESTINO in text_no_space:
                    if monto_detected and abs(monto_detected - monto) <= max(2000, int(monto*0.05)):
                        ocr_ok = True
                    else:
                        if monto_detected:
                            ocr_ok = abs(monto_detected - monto) <= max(2000, int(monto*0.05))
                            if not ocr_ok:
                                ocr_reason = f"Monto detectado ({monto_detected}) no coincide con {monto}."
                        else:
                            ocr_ok = False
                            ocr_reason = "No se detectó el monto en el comprobante."
                else:
                    ocr_ok = False
                    ocr_reason = "No se detectó el número destino en la imagen."
            except Exception as e:
                ocr_ok = False
                ocr_reason = f"OCR falló: {e}"
        else:
            ocr_ok = False
            ocr_reason = "OCR no disponible en este entorno."

        fecha_inversion = datetime.date.today()
        fecha_pago = (fecha_inversion + datetime.timedelta(days=3)).strftime("%d/%m/%Y")

        conn = get_conn(); cur = conn.cursor()
        cur.execute("INSERT INTO inversiones (user_id, monto, fecha_inversion, fecha_pago, estado, comprobante_path, ocr_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, monto, str(fecha_inversion), fecha_pago, "Pendiente", saved_path, ocr_text))
        conn.commit(); conn.close()

        if ocr_ok:
            safe_send(chat_id, f"✅ Comprobante verificado preliminarmente (OCR). Está pendiente de aprobación por el administrador.\n📅 Fecha estimada de pago: {fecha_pago}")
            safe_send(ADMIN_ID, f"📥 Nuevo comprobante PENDIENTE de {message.from_user.first_name} (${fmt_money(monto)}). OCR OK. ID usuario: {user_id}")
        else:
            safe_send(chat_id, f"⚠️ No se pudo verificar automáticamente el comprobante: {ocr_reason}\nEl administrador lo revisará manualmente.")
            safe_send(ADMIN_ID, f"📥 Nuevo comprobante PENDIENTE de {message.from_user.first_name} (${fmt_money(monto)}). OCR: {ocr_reason}\nPath: {saved_path}")
    except Exception:
        traceback.print_exc()
        safe_send(message.chat.id, "⚠️ Ocurrió un error procesando el comprobante. Intenta nuevamente.")

# ---------------- Panel admin ----------------
@bot.message_handler(func=lambda m: m.text == "📈 Panel admin")
def panel_admin(m):
    if m.from_user.id != ADMIN_ID:
        safe_send(m.chat.id, "❌ No tienes acceso.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📊 Estadísticas"), types.KeyboardButton("🔎 Revisar pendientes"))
    markup.add(types.KeyboardButton("📜 Historial"), types.KeyboardButton("🔙 Volver"))
    safe_send(m.chat.id, "Panel admin - selecciona una opción:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 Estadísticas")
def admin_stats(m):
    if m.from_user.id != ADMIN_ID:
        return
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM usuarios"); total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inversiones WHERE estado='Pendiente'"); pend = cur.fetchone()[0]
    cur.execute("SELECT SUM(monto) FROM inversiones WHERE estado='Aprobado'"); s = cur.fetchone()[0] or 0
    conn.close()
    safe_send(m.chat.id, f"📊 Usuarios: {total_users}\nInversiones pendientes: {pend}\nTotal invertido (aprobado): ${fmt_money(s)}")

@bot.message_handler(func=lambda m: m.text == "🔎 Revisar pendientes")
def admin_revisar_pendientes(m):
    if m.from_user.id != ADMIN_ID:
        return
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id, user_id, monto, fecha_inversion, fecha_pago, comprobante_path, ocr_text FROM inversiones WHERE estado='Pendiente' ORDER BY id ASC")
    rows = cur.fetchall(); conn.close()
    if not rows:
        safe_send(m.chat.id, "✅ No hay inversiones pendientes.")
        return
    for r in rows:
        inv_id, uid, monto, finv, fpago, path, ocr_text = r
        text = f"ID:{inv_id} · Usuario:{uid} · Monto:${fmt_money(monto)} · Fecha pago:{fpago}\nOCR: {ocr_text[:200] if ocr_text else 'N/A'}"
        if path and os.path.exists(path):
            try:
                bot.send_photo(m.chat.id, open(path, "rb"), caption=text)
            except:
                safe_send(m.chat.id, text)
        else:
            safe_send(m.chat.id, text)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Aprobar", callback_data=f"APP|{inv_id}"),
               types.InlineKeyboardButton("❌ Rechazar", callback_data=f"REJ|{inv_id}"))
        safe_send(m.chat.id, "Acciones:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("APP|") or c.data.startswith("REJ|")))
def admin_process_callback(c):
    try:
        if c.from_user.id != ADMIN_ID:
            return bot.answer_callback_query(c.id, "No autorizado.")
        action, inv_id = c.data.split("|")
        inv_id = int(inv_id)
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT user_id, monto, fecha_pago FROM inversiones WHERE id=?", (inv_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return bot.answer_callback_query(c.id, "Inversión no encontrada.")
        uid, monto, fecha_pago = row
        if action == "APP":
            cur.execute("UPDATE inversiones SET estado='Aprobado' WHERE id=?", (inv_id,))
            ganancia = int(monto * 0.6)
            cur.execute("UPDATE usuarios SET total_invertido = total_invertido + ?, ganancia_total = ganancia_total + ? WHERE user_id=?", (monto, ganancia, uid))
            conn.commit(); conn.close()
            bot.answer_callback_query(c.id, "Inversión aprobada.")
            safe_send(ADMIN_ID, f"✅ Inversión {inv_id} aprobada.")
            try:
                safe_send(uid, f"✅ Tu inversión de ${fmt_money(monto)} ha sido aprobada.\n💰 Ganancia estimada: ${fmt_money(ganancia)}\n📅 Recibirás tu pago el {fecha_pago}")
            except:
                pass
        else:
            cur.execute("UPDATE inversiones SET estado='Rechazado' WHERE id=?", (inv_id,))
            conn.commit(); conn.close()
            bot.answer_callback_query(c.id, "Inversión rechazada.")
            safe_send(ADMIN_ID, f"❌ Inversión {inv_id} rechazada.")
            try:
                safe_send(uid, f"❌ Tu comprobante de ${fmt_money(monto)} fue rechazado. Revisa la información y vuelve a enviar uno válido.")
            except:
                pass
    except Exception:
        traceback.print_exc()
        try:
            bot.answer_callback_query(c.id, "Error procesando acción.")
        except:
            pass

@bot.message_handler(func=lambda m: m.text == "📜 Historial")
def admin_historial(m):
    if m.from_user.id != ADMIN_ID:
        return
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id, user_id, monto, estado, fecha_inversion FROM inversiones ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall(); conn.close()
    if not rows:
        safe_send(m.chat.id, "No hay historial.")
        return
    s = "📜 Historial (últimos 50):\n"
    for r in rows:
        s += f"ID {r[0]} | U:{r[1]} | ${fmt_money(r[2])} | {r[3]} | Inv:{r[4]}\n"
    safe_send(m.chat.id, s)

@bot.message_handler(func=lambda m: m.text == "🔙 Volver")
def admin_volver(m):
    safe_send(m.chat.id, "Volviendo al menú...", reply_markup=menu_principal_for(m.from_user.id))

# ---------------- Fallback handler ----------------
@bot.message_handler(func=lambda m: True)
def fallback(m):
    safe_send(m.chat.id, "Selecciona una opción:", reply_markup=menu_principal_for(m.from_user.id))

# ---------------- Polling con reconexión ----------------
def start_polling_with_retries():
    print("🤖 InversionesCT iniciado. TESSERACT_AVAILABLE =", TESSERACT_AVAILABLE)
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=60)
        except Exception as e:
            print("⚠️ Polling error:", e)
            traceback.print_exc()
            time.sleep(10)

if __name__ == "__main__":
    start_polling_with_retries()

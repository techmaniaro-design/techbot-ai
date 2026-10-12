import os
import io
import json
import uuid
import requests
import PyPDF2
import docx2txt
import pytesseract
from PIL import Image
import streamlit as st
from openai import OpenAI
from duckduckgo_search import DDGS
from supabase import create_client, Client
from streamlit_cookies_controller import CookieController

# --- CONFIGURARE INIȚIALĂ ---
st.set_page_config(page_title="TechBot AI", page_icon="🤖", layout="wide")
st.title("🤖 TechBot AI")
st.caption("Asistent cu memorie privată, căutare Web și analiză de Documente.")

# ====================================================================
# --- MANAGER DE COOKIES ---
# ====================================================================
# Trebuie inițializat fix la început pentru a putea "vorbi" cu browserul tău
controller = CookieController()

url_baza_date = "https://yunipdkppxqnnrjebdtc.supabase.co" 
cheie_baza_date = st.secrets["SUPABASE_KEY"]
cheie_groq = st.secrets["GROQ_API_KEY"]

client = OpenAI(api_key=cheie_groq, base_url="https://api.groq.com/openai/v1")
supabase: Client = create_client(url_baza_date, cheie_baza_date)

# ====================================================================
# --- SISTEM DE AUTENTIFICARE INTELIGENT ---
# ====================================================================
if "user_id" not in st.session_state: 
    st.session_state.user_id = None
if "user_email" not in st.session_state: 
    st.session_state.user_email = None

# AICI E MAGIA: Citim întârziat cookie-ul din browser
cookie_id = controller.get('techbot_user_id')
cookie_email = controller.get('techbot_user_email')

# Dacă browser-ul a trimis cookie-ul, dar noi suntem încă "nelogați", ne logăm automat!
if cookie_id and st.session_state.user_id is None:
    st.session_state.user_id = cookie_id
    st.session_state.user_email = cookie_email
    st.rerun() # Reîncărcăm pagina instant ca să ascundem ecranul de Login

# Ecranul de Login (se afișează doar dacă cookie-ul e gol)
if st.session_state.user_id is None:
    st.info("🔒 Trebuie să te autentifici pentru a accesa asistentul.")
    
    tab_login, tab_register = st.tabs(["Intră în cont", "Creează cont nou"])
    
    with tab_login:
        email_in = st.text_input("Email", key="login_email")
        pass_in = st.text_input("Parolă", type="password", key="login_pass")
        if st.button("Loghează-te", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": email_in, "password": pass_in})
                
                # Salvăm datele în browser-ul utilizatorului (valabile 30 de zile)
                controller.set('techbot_user_id', res.user.id, max_age=30*24*60*60)
                controller.set('techbot_user_email', res.user.email, max_age=30*24*60*60)
                
                st.session_state.user_id = res.user.id
                st.session_state.user_email = res.user.email
                
                st.success("✅ Autentificare reușită! Se încarcă...")
                st.rerun()
            except Exception:
                st.error("❌ Eroare: Email sau parolă incorecte.")
                
    with tab_register:
        email_up = st.text_input("Email ", key="reg_email")
        pass_up = st.text_input("Parolă (minim 6 caractere)", type="password", key="reg_pass")
        if st.button("Creează Cont", use_container_width=True):
            try:
                res = supabase.auth.sign_up({"email": email_up, "password": pass_up})
                
                # Salvăm datele în browser la creare cont
                controller.set('techbot_user_id', res.user.id, max_age=30*24*60*60)
                controller.set('techbot_user_email', res.user.email, max_age=30*24*60*60)
                
                st.session_state.user_id = res.user.id
                st.session_state.user_email = res.user.email
                
                st.success("✅ Cont creat cu succes! Se încarcă...")
                st.rerun()
            except Exception as e:
                st.error(f"Eroare la creare cont: {e}")
                
    st.stop() # Dacă nu e logat, nu rulăm restul codului

# ====================================================================
# --- APLICAȚIA PRINCIPALĂ (Rulează doar după Logare) ---
# ====================================================================
USER_ID = st.session_state.user_id

def obtine_lista_conversatii():
    try:
        response = supabase.table("chats").select("id, title").eq("user_id", USER_ID).order("created_at", desc=True).execute()
        return response.data
    except Exception: return []

def creeaza_conversatie_noua(titlu="Conversație Nouă"):
    try:
        response = supabase.table("chats").insert({"user_id": USER_ID, "title": titlu}).execute()
        return response.data[0]['id']
    except Exception: return None

def salveaza_mesaj_db(chat_id, role, content):
    try:
        supabase.table("chat_history").insert({
             "user_session": USER_ID, "chat_id": chat_id, "role": role, "content": content
        }).execute()
    except Exception: pass

def incarca_istoric_db(chat_id):
    if not chat_id: return []
    try:
        response = supabase.table("chat_history").select("role, content").eq("chat_id", chat_id).order("created_at").execute()
        return response.data
    except Exception: return []

def citeste_fisier(uploaded_file):
    nume = uploaded_file.name.lower()
    try:
        if nume.endswith('.pdf'):
            text = ""
            reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.getvalue()))
            for page in reader.pages:
                extras = page.extract_text()
                if extras: text += extras + "\n"
            return text
        elif nume.endswith('.docx'):
            return docx2txt.process(io.BytesIO(uploaded_file.getvalue()))
        elif nume.endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            imagine = Image.open(io.BytesIO(uploaded_file.getvalue()))
            text_extras = pytesseract.image_to_string(imagine)
            return f"[Text extras din imaginea {nume}]:\n{text_extras}"
        else:
            return uploaded_file.getvalue().decode("utf-8")
    except UnicodeDecodeError: return f"Eroare: {nume} este un fișier binar."
    except Exception as e: return f"Eroare la procesare: {e}"

def cauta_pe_internet(query):
    try: return "\n".join([rez['body'] for rez in DDGS().text(query, max_results=3)])
    except Exception as e: return f"Eroare: {str(e)}"

def citeste_cod_github(url):
    try:
        raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        r = requests.get(raw_url)
        if r.status_code == 200: return r.text[:5000]
        return f"Eroare HTTP: {r.status_code}"
    except Exception as e: return f"Eroare: {str(e)}"

tools = [{"type": "function", "function": {"name": "cauta_pe_internet", "description": "Caută pe net.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}, {"type": "function", "function": {"name": "citeste_cod_github", "description": "Citește cod din GitHub.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}}]

if "current_chat_id" not in st.session_state: st.session_state.current_chat_id = None
if "mesaje" not in st.session_state: st.session_state.mesaje = []
if "fisiere_procesate" not in st.session_state: st.session_state.fisiere_procesate = []

with st.sidebar:
    st.caption(f"👤 Logat ca: **{st.session_state.user_email}**")
    
    with st.expander("⚙️ Setări Cont"):
        st.write("Schimbă parola contului tău:")
        new_password = st.text_input("Parolă nouă", type="password", key="new_pass")
        if st.button("Actualizează Parola", use_container_width=True):
            if len(new_password) >= 6:
                try:
                    supabase.auth.update_user({"password": new_password})
                    st.success("✅ Parola a fost schimbată!")
                except Exception as e:
                    st.error(f"Eroare: {e}")
            else:
                st.warning("Parola trebuie să aibă minim 6 caractere.")

    if st.button("🚪 Deconectare", use_container_width=True):
        # Ștergem cookie-urile definitiv la deconectare!
        controller.remove('techbot_user_id')
        controller.remove('techbot_user_email')
        
        st.session_state.user_id = None
        st.session_state.user_email = None
        st.session_state.current_chat_id = None
        st.session_state.mesaje = []
        st.session_state.fisiere_procesate = []
        st.rerun()
        
    st.divider()
    
    st.header("Conversațiile tale")
    if st.button("➕ Conversație Nouă", use_container_width=True):
        st.session_state.current_chat_id = None
        st.session_state.mesaje = []
        st.session_state.fisiere_procesate = []
        st.rerun()
        
    st.divider()
    
    lista_conversatii = obtine_lista_conversatii()
    for conv in lista_conversatii:
        if st.button(conv["title"], key=conv["id"], use_container_width=True):
            st.session_state.current_chat_id = conv["id"]
            st.session_state.fisiere_procesate = []
            st.session_state.mesaje = incarca_istoric_db(conv["id"])
            if not st.session_state.mesaje:
                prompt = "Ești un asistent tehnic expert."
                st.session_state.mesaje = [{"role": "system", "content": prompt}]
                salveaza_mesaj_db(conv["id"], "system", prompt)
            st.rerun()

if st.session_state.current_chat_id is None and not st.session_state.mesaje:
     st.session_state.mesaje = [{"role": "system", "content": "Ești un asistent expert. Citește fișierele cu atenție și folosește-le ca bază."}]

for idx, msg in enumerate(st.session_state.mesaje):
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.markdown(content)
            if role == "assistant":
                st.download_button("💾 Salvează Răspunsul", data=content, file_name=f"raspuns_{idx}.txt", key=f"dl_{idx}")

with st.popover("📎 Atașează un fișier", help="Fisiere PDF, Word, TXT, Scripturi sau Imagini."):
    fisier_incarcat = st.file_uploader("Trage fișierul aici", label_visibility="collapsed")

needs_rerun = False
if fisier_incarcat and fisier_incarcat.name not in st.session_state.fisiere_procesate:
    text_extras = citeste_fisier(fisier_incarcat)
    
    if st.session_state.current_chat_id is None:
        st.session_state.current_chat_id = creeaza_conversatie_noua(titlu=f"Analiză {fisier_incarcat.name}")
        salveaza_mesaj_db(st.session_state.current_chat_id, "system", st.session_state.mesaje[0]["content"])
    
    mesaj_fisier = f"📄 **Am încărcat fișierul:** `{fisier_incarcat.name}`\n\n**Conținut:**\n```\n{text_extras[:15000]}\n```\n\nFolosește aceste date."
    st.session_state.mesaje.append({"role": "user", "content": mesaj_fisier})
    salveaza_mesaj_db(st.session_state.current_chat_id, "user", mesaj_fisier)
    st.session_state.fisiere_procesate.append(fisier_incarcat.name)
    needs_rerun = True

if user_input := st.chat_input("Scrie mesajul tău..."):
    if st.session_state.current_chat_id is None:
        titlu_scurt = user_input[:20] + "..." if len(user_input) > 20 else user_input
        st.session_state.current_chat_id = creeaza_conversatie_noua(titlu=titlu_scurt)
        salveaza_mesaj_db(st.session_state.current_chat_id, "system", st.session_state.mesaje[0]["content"])
        needs_rerun = True

    with st.chat_message("user"): st.markdown(user_input)
    st.session_state.mesaje.append({"role": "user", "content": user_input})
    salveaza_mesaj_db(st.session_state.current_chat_id, "user", user_input) 
    
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("Gândesc...")
        
        try:
            bot_reply = ""
            while True:
                response = client.chat.completions.create(model="openai/gpt-oss-120b", messages=st.session_state.mesaje, tools=tools, tool_choice="auto")
                msg_curent = response.choices[0].message
                
                if not msg_curent.tool_calls:
                    bot_reply = msg_curent.content
                    break
                
                st.session_state.mesaje.append(msg_curent)
                
                for tool_call in msg_curent.tool_calls:
                    argumente = json.loads(tool_call.function.arguments)
                    
                    if tool_call.function.name == "cauta_pe_internet":
                        query = argumente.get("query")
                        placeholder.markdown(f"🔄 **Caut pe net:** `{query}`...")
                        rez_live = cauta_pe_internet(query)
                    elif tool_call.function.name == "citeste_cod_github":
                        url = argumente.get("url")
                        placeholder.markdown(f"💻 **Citesc codul:** `{url}`...")
                        rez_live = citeste_cod_github(url)
                    else: rez_live = "Eroare: Unealtă inexistentă."
                        
                    st.session_state.mesaje.append({"role": "tool", "tool_call_id": tool_call.id, "content": rez_live})
                    
            if not bot_reply: bot_reply = "Proces încheiat."
            placeholder.markdown(bot_reply)
            st.session_state.mesaje.append({"role": "assistant", "content": bot_reply})
            salveaza_mesaj_db(st.session_state.current_chat_id, "assistant", bot_reply)
            st.download_button("💾 Salvează Răspunsul", data=bot_reply, file_name="raspuns.txt", key=f"dl_nou_{uuid.uuid4().hex[:6]}")
        except Exception as e:
            placeholder.markdown(f"⚠️ Eroare critică: {e}")
            
if needs_rerun: st.rerun()

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

# --- CONFIGURARE INIȚIALĂ ---
st.set_page_config(page_title="TechBot AI", page_icon="🤖", layout="wide")
st.title("🤖 TechBot AI")
st.caption("Asistent cu memorie privată, căutare Web și analiză de Documente.")

# ====================================================================
url_baza_date = "https://yunipdkppxqnnrjebdtc.supabase.co" 
cheie_baza_date = st.secrets["SUPABASE_KEY"]
cheie_groq = st.secrets["GROQ_API_KEY"]
# ====================================================================

client = OpenAI(api_key=cheie_groq, base_url="https://api.groq.com/openai/v1")
supabase: Client = create_client(url_baza_date, cheie_baza_date)

# ====================================================================
# --- SISTEM DE AUTENTIFICARE SOLID (Fără email de confirmare) ---
# ====================================================================
if "user_id" not in st.session_state: 
    st.session_state.user_id = None
if "user_email" not in st.session_state: 
    st.session_state.user_email = None

if st.session_state.user_id is None:
    st.info("🔒 Trebuie să te autentifici pentru a accesa asistentul.")
    
    # Doar cele două ecrane esențiale
    tab_login, tab_register = st.tabs(["Intră în cont", "Creează cont nou"])
    
    with tab_login:
        email_in = st.text_input("Email", key="login_email")
        pass_in = st.text_input("Parolă", type="password", key="login_pass")
        if st.button("Loghează-te", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": email_in, "password": pass_in})
                st.session_state.user_id = res.user.id
                st.session_state.user_email = res.user.email
                st.rerun()
            except Exception:
                st.error("❌ Eroare: Email sau parolă incorecte.")
                
    with tab_register:
        email_up = st.text_input("Email", key="reg_email")
        pass_up = st.text_input("Parolă (minim 6 caractere)", type="password", key="reg_pass")
        if st.button("Creează Cont", use_container_width=True):
            try:
                # Creăm contul și îl logăm direct 
                res = supabase.auth.sign_up({"email": email_up, "password": pass_up})
                st.session_state.user_id = res.user.id
                st.session_state.user_email = res.user.email
                st.success("✅ Cont creat cu succes! Te conectăm imediat...")
                st.rerun()
            except Exception as e:
                st.error(f"Eroare la creare cont: {e}")
                
    st.stop() 

# --- APLICAȚIA PRINCIPALĂ (DOAR PENTRU UTILIZATORII LOGAȚI) ---
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
        st.session_state.user_id = None
        st.session_state.user_email = None
        st.session_state.current_chat_id = None
        st.session_state.mesaje = []
        st.session_state.fisiere_procesate = []
        st.rerun()
        
    st.divider()
    
    st

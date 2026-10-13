import os
import io
import json
import uuid
import time
import requests
import PyPDF2
import docx2txt
import pytesseract
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from duckduckgo_search import DDGS
from supabase import create_client, Client
import extra_streamlit_components as stx

# --- CONFIGURARE INIȚIALĂ ---
st.set_page_config(page_title="TechBot AI", page_icon="🤖", layout="wide")

# ====================================================================
# --- MANAGER DE COOKIES ---
# ====================================================================
with st.sidebar:
    cookie_manager = stx.CookieManager(key="cookie_manager")

if "prima_incarcare" not in st.session_state:
    st.session_state.prima_incarcare = True
    time.sleep(0.5) 
    st.rerun()

st.title("🤖 TechBot AI")
st.caption("Asistent cu memorie privată, căutare Web și analiză de Documente.")

url_baza_date = "https://yunipdkppxqnnrjebdtc.supabase.co" 
cheie_baza_date = st.secrets["SUPABASE_KEY"]
cheie_groq = st.secrets["GROQ_API_KEY"]

client = OpenAI(api_key=cheie_groq, base_url="https://api.groq.com/openai/v1")
supabase: Client = create_client(url_baza_date, cheie_baza_date)

# ====================================================================
# --- SISTEM DE AUTENTIFICARE ---
# ====================================================================
if "user_id" not in st.session_state: 
    st.session_state.user_id = None
if "user_email" not in st.session_state: 
    st.session_state.user_email = None
if "is_logged_out" not in st.session_state:
    st.session_state.is_logged_out = False

c_id = cookie_manager.get(cookie="techbot_uid")
c_email = cookie_manager.get(cookie="techbot_email")

if st.session_state.is_logged_out:
    c_id = None
    c_email = None

if c_id and st.session_state.user_id is None:
    st.session_state.user_id = c_id
    st.session_state.user_email = c_email

login_container = st.empty()

if st.session_state.user_id is None:
    with login_container.container():
        st.info("🔒 Trebuie să te autentifici pentru a accesa asistentul.")
        
        tab_login, tab_register = st.tabs(["Intră în cont", "Creează cont nou"])
        
        with tab_login:
            email_in = st.text_input("Email", key="login_email")
            pass_in = st.text_input("Parolă", type="password", key="login_pass")
            if st.button("Loghează-te", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email_in, "password": pass_in})
                    
                    cookie_manager.set("techbot_uid", res.user.id, max_age=30*24*60*60, key="login_uid")
                    cookie_manager.set("techbot_email", res.user.email, max_age=30*24*60*60, key="login_email")
                    
                    st.session_state.user_id = res.user.id
                    st.session_state.user_email = res.user.email
                    st.session_state.is_logged_out = False 
                    
                    time.sleep(0.5) 
                    st.rerun()
                except Exception:
                    st.error("❌ Eroare: Email sau parolă incorecte.")
                    
        with tab_register:
            email_up = st.text_input("Email ", key="reg_email")
            pass_up = st.text_input("Parolă (minim 6 caractere)", type="password", key="reg_pass")
            if st.button("Creează Cont", use_container_width=True):
                try:
                    res = supabase.auth.sign_up({"email": email_up, "password": pass_up})
                    
                    cookie_manager.set("techbot_uid", res.user.id, max_age=30*24*60*60, key="reg_uid")
                    cookie_manager.set("techbot_email", res.user.email, max_age=30*24*60*60, key="reg_email")
                    
                    st.session_state.user_id = res.user.id
                    st.session_state.user_email = res.user.email
                    st.session_state.is_logged_out = False
                    
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Eroare la creare cont: {e}")
                    
    st.stop() 

# ====================================================================
# --- APLICAȚIA PRINCIPALĂ ---
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
            imagine = Image.open(io.Bytes

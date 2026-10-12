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
st.caption("Asistent cu memorie, căutare Web, analiză GitHub și procesare avansată de Documente.")

# ====================================================================
url_baza_date = "https://yunipdkppxqnnrjebdtc.supabase.co" 
cheie_baza_date = st.secrets["SUPABASE_KEY"]
cheie_groq = st.secrets["GROQ_API_KEY"]
# ====================================================================

client = OpenAI(api_key=cheie_groq, base_url="https://api.groq.com/openai/v1")
supabase: Client = create_client(url_baza_date, cheie_baza_date)
USER_ID = "utilizator_test_1"

# --- FUNCȚII BAZĂ DE DATE ---
def obtine_lista_conversatii():
    try:
        response = supabase.table("chats").select("id, title").eq("user_id", USER_ID).order("created_at", desc=True).execute()
        return response.data
    except Exception: 
        return []

def creeaza_conversatie_noua(titlu="Conversație Nouă"):
    try:
        response = supabase.table("chats").insert({"user_id": USER_ID, "title": titlu}).execute()
        return response.data[0]['id']
    except Exception: 
        return None

def salveaza_mesaj_db(chat_id, role, content):
    try:
        supabase.table("chat_history").insert({
             "user_session": USER_ID, "chat_id": chat_id, "role": role, "content": content
        }).execute()
    except Exception: 
        pass

def incarca_istoric_db(chat_id):
    if not chat_id: return []
    try:
        response = supabase.table("chat_history").select("role, content").eq("chat_id", chat_id).order("created_at").execute()
        return response.data
    except Exception: 
        return []

# --- FUNCȚIE UNIVERSALĂ DE CITIRE FIȘIERE ---
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
    except UnicodeDecodeError:
        return f"Eroare: {nume} este un fișier binar."
    except Exception as e:
        return f"Eroare la procesarea fișierului {nume}: {e}"

# --- TOOLS ---
def cauta_pe_internet(query):
    try:
        return "\n".join([rez['body'] for rez in DDGS().text(query, max_results=3)])
    except Exception as e: 
        return f"Eroare: {str(e)}"

def citeste_cod_github(url):
    try:
        raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        r = requests.get(raw_url)
        if r.status_code == 200: return r.text[:5000]
        return f"Eroare HTTP: {r.status_code}"
    except Exception as e: 
        return f"Eroare: {str(e)}"

tools = [
    {"type": "function", "function": {"name": "cauta_pe_internet", "description": "Caută informații pe internet.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}, 
    {"type": "function", "function": {"name": "citeste_cod_github", "description": "Citește cod sursă din GitHub.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}}
]

# --- MANAGEMENTUL STĂRII ---
if "current_chat_id" not in st.session_state: 
    st.session_state.current_chat_id = None

if "mesaje" not in st.session_state: 
    st.session_state.mesaje = []

if "fisiere_procesate" not in st.session_state: 
    st.session_state.fisiere_procesate = []

# --- SIDEBAR (MENIU LATERAL) - DOAR PENTRU ISTORIC ---
with st.sidebar:
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

# --- ZONA PRINCIPALĂ DE CHAT ---
if st.session_state.current_chat_id is None and not st.session_state.mesaje:
     st.session_state.mesaje = [{"role": "system", "content": "Ești un asistent tehnic expert. Când utilizatorul îți dă un fișier, cod sau printscreen, citește-l cu atenție și folosește-l ca bază pentru răspuns."}]

# 1. Afișăm istoricul mesajelor
for idx, msg in enumerate(st.session_state.mesaje):
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.markdown(content)
            if role == "assistant":
                st.download_button("💾 Salvează Răspunsul (.txt)", data=content, file_name=f"raspuns_bot_{idx}.txt", key=f"dl_{idx}")

# 2. BUTONUL COMPACT DE UPLOAD (Agrafă)
with st.popover("📎 Atașează un fișier", help="Ce poți uploada: Fisiere PDF, Word, TXT, Scripturi (.py, .js) sau Imagini/Printscreen-uri."):
    fisier_incarcat = st.file_uploader("Alege sau trage fișierul aici", label_visibility="collapsed")

# --- LOGICA DE PROCESARE A FIȘIERULUI ---
needs_rerun = False
if fisier_incarcat and fisier_incarcat.name not in st.session_state.fisiere_procesate:
    text_extras = citeste_fisier(fisier_incarcat)
    
    if st.session_state.current_chat_id is None:
        st.session_state.current_chat_id = creeaza_conversatie_noua(titlu=f"Analiză {fisier_incarcat.name}")
        salveaza_mesaj_db(st.session_state.current_chat_id, "system", st.session_state.mesaje[0]["content"])
    
    mesaj_fisier = f"📄 **Am încărcat fișierul:** `{fisier_incarcat.name}`\n\n**Conținut extras:**\n```\n{text_extras[:15000]}\n```\n\nFolosește aceste date pentru următoarele mele instrucțiuni."
    
    st.session_state.mesaje.append({"role": "user", "content": mesaj_fisier})
    salveaza_mesaj_db(st.session_state.current_chat_id, "user", mesaj_fisier)
    
    st.session_state.fisiere_procesate.append(fisier_incarcat.name)
    needs_rerun = True

# --- LOGICA DE CHAT (Bara de text de jos) ---
if user_input := st.chat_input("Scrie mesajul tău sau instrucțiuni pentru fișier..."):
    
    if st.session_state.current_chat_id is None:
        titlu_scurt = user_input[:20] + "..." if len(user_input) > 20 else user_input
        st.session_state.current_chat_id = creeaza_conversatie_noua(titlu=titlu_scurt)
        salveaza_mesaj_db(st.session_state.current_chat_id, "system", st.session_state.mesaje[0]["content"])
        needs_rerun = True

    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.mesaje.append({"role": "user", "content": user_input})
    salveaza_mesaj_db(st.session_state.current_chat_id, "user", user_input) 
    
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("Gândesc...")
        
        try:
            bot_reply = ""
            while True:
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=st.session_state.mesaje,
                    tools=tools,
                    tool_choice="auto"
                )
                
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
                    else:
                        rez_live = "Eroare: Unealtă inexistentă."
                        
                    st.session_state.mesaje.append({"role": "tool", "tool_call_id": tool_call.id, "content": rez_live})
                    
            if not bot_reply: bot_reply = "Procesul s-a încheiat fără text generat."
                
            placeholder.markdown(bot_reply)
            st.session_state.mesaje.append({"role": "assistant", "content": bot_reply})
            salveaza_mesaj_db(st.session_state.current_chat_id, "assistant", bot_reply)
            
            st.download_button("💾 Salvează Răspunsul (.txt)", data=bot_reply, file_name="raspuns_formatat.txt", key=f"dl_nou_{uuid.uuid4().hex[:6]}")
            
        except Exception as e:
            placeholder.markdown(f"⚠️ Eroare critică: {e}")
            
if needs_rerun:
    st.rerun()

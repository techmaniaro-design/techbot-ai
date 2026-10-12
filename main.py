import os
import json
import uuid
import requests
import streamlit as st
from openai import OpenAI
from duckduckgo_search import DDGS
from supabase import create_client, Client

# --- CONFIGURARE INIȚIALĂ ---
st.set_page_config(page_title="TechBot AI", page_icon="🤖", layout="centered")
st.title("🤖 TechBot AI")
st.caption("Asistent tehnic cu memorie permanentă, căutare Web și analiză cod GitHub.")

# ====================================================================
url_baza_date = "https://yunipdkppxqnnrjebdtc.supabase.co" 

# TE ROG SĂ PUI CHEILE TALE AICI ÎNTRE GHILIMELE:
cheie_baza_date = st.secrets["SUPABASE_KEY"]
cheie_groq = st.secrets["GROQ_API_KEY"]

client = OpenAI(api_key=cheie_groq, base_url="https://api.groq.com/openai/v1")
supabase: Client = create_client(url_baza_date, cheie_baza_date)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# --- FUNCȚII DB ---
def salveaza_mesaj_db(role, content):
    try:
        supabase.table("chat_history").insert({
            "user_session": st.session_state.session_id,
            "role": role,
            "content": content
        }).execute()
    except Exception as e:
        print(f"Eroare DB la salvare: {e}")

def incarca_istoric_db():
    try:
        response = supabase.table("chat_history").select("role, content").eq("user_session", st.session_state.session_id).order("created_at").execute()
        return response.data
    except Exception as e:
        return []

# --- TOOL 1: CĂUTARE WEB ---
def cauta_pe_internet(query):
    try:
        return "\n".join([rez['body'] for rez in DDGS().text(query, max_results=3)])
    except Exception as e:
        return f"Eroare: {str(e)}"

# --- TOOL 2: CITIRE GITHUB ---
def citeste_cod_github(url):
    try:
        raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        r = requests.get(raw_url)
        if r.status_code == 200:
            return r.text[:5000] # Limităm la 5000 de caractere
        return f"Eroare: Nu am putut citi fișierul. Cod HTTP: {r.status_code}"
    except Exception as e:
        return f"Eroare: {str(e)}"

# --- LISTA DE TOOLS PENTRU AI ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "cauta_pe_internet",
            "description": "Caută pe net informații recente IT/hardware.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "citeste_cod_github",
            "description": "Citește codul sursă direct dintr-un link public de GitHub.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "Link-ul complet GitHub"}}, "required": ["url"]}
        }
    }
]

# --- INIȚIALIZARE CHAT ---
if "mesaje" not in st.session_state:
    istoric = incarca_istoric_db()
    if istoric:
        st.session_state.mesaje = istoric
    else:
        system_prompt = "Ești un asistent tehnic expert. Poți căuta pe net și citi cod de pe GitHub."
        st.session_state.mesaje = [{"role": "system", "content": system_prompt}]
        salveaza_mesaj_db("system", system_prompt)

# Afișăm istoricul vizual
for msg in st.session_state.mesaje:
    # Verificăm dacă mesajul este dicționar (din DB) sau obiect complex (de la funcții)
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.markdown(content)

# --- LOGICA PRINCIPALĂ ---
if user_input := st.chat_input("Ex: Ce face codul de la acest link GitHub?"):
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.mesaje.append({"role": "user", "content": user_input})
    salveaza_mesaj_db("user", user_input) 
    
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("Gândesc...")
        
        try:
            bot_reply = ""
            # Folosim o buclă infinită pentru a permite AI-ului să investigheze
            while True:
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=st.session_state.mesaje,
                    tools=tools,
                    tool_choice="auto"
                )
                
                msg_curent = response.choices[0].message
                
                # 1. Dacă nu vrea unelte, înseamnă că are textul final pregătit! Oprim bucla.
                if not msg_curent.tool_calls:
                    bot_reply = msg_curent.content
                    break
                
                # 2. Dacă vrea să folosească unelte, le executăm
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
                        # Protecție dacă AI-ul "halucinează" unelte false
                        rez_live = "Eroare: Această unealtă nu există. Explică direct folosind datele extrase."
                        
                    # Salvăm rezultatul uneltei. Bucla se va repeta pentru ca AI-ul să citească rezultatul!
                    st.session_state.mesaje.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": rez_live
                    })
                    
            # Bucla s-a încheiat. Afișăm pe ecran și salvăm în baza de date!
            if not bot_reply:
                bot_reply = "Fișierul a fost citit, dar asistentul nu a formulat o explicație."
                
            placeholder.markdown(bot_reply)
            st.session_state.mesaje.append({"role": "assistant", "content": bot_reply})
            salveaza_mesaj_db("assistant", bot_reply)
            
        except Exception as e:
            placeholder.markdown(f"⚠️ Eroare critică la generare: {e}")

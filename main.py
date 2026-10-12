import os
import json
import uuid
import requests
import streamlit as st
from openai import OpenAI
from duckduckgo_search import DDGS
from supabase import create_client, Client

# --- CONFIGURARE INIȚIALĂ ---
st.set_page_config(page_title="TechBot AI", page_icon="🤖", layout="wide")
st.title("🤖 TechBot AI")
st.caption("Asistent tehnic cu memorie permanentă, căutare Web și analiză cod GitHub.")

# ====================================================================
url_baza_date = "https://yunipdkppxqnnrjebdtc.supabase.co" 
# Preia cheile din seiful Streamlit Cloud
cheie_baza_date = st.secrets["SUPABASE_KEY"]
cheie_groq = st.secrets["GROQ_API_KEY"]
# ====================================================================

client = OpenAI(api_key=cheie_groq, base_url="https://api.groq.com/openai/v1")
supabase: Client = create_client(url_baza_date, cheie_baza_date)

# ID-ul utilizatorului (hardcodat pentru test, până facem sistem de login real)
USER_ID = "utilizator_test_1"

# --- FUNCȚII PENTRU GESTIONAREA CONVERSAȚIILOR (CHATS) ---
def obtine_lista_conversatii():
    """Aduce din DB toate conversațiile acestui utilizator"""
    try:
        response = supabase.table("chats").select("id, title").eq("user_id", USER_ID).order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Eroare la citire lista chat-uri: {e}")
        return []

def creeaza_conversatie_noua(titlu="Conversație Nouă"):
    """Creează un 'dosar' nou de conversație în DB și returnează ID-ul lui"""
    try:
        response = supabase.table("chats").insert({
            "user_id": USER_ID,
            "title": titlu
        }).execute()
        return response.data[0]['id']
    except Exception as e:
        print(f"Eroare la creare chat: {e}")
        return None

def actualizeaza_titlu_conversatie(chat_id, titlu_nou):
    """Schimbă titlul conversației după primul mesaj"""
    try:
         supabase.table("chats").update({"title": titlu_nou}).eq("id", chat_id).execute()
    except Exception as e:
        print(f"Eroare la update titlu: {e}")

# --- FUNCȚII PENTRU GESTIONAREA MESAJELOR ---
def salveaza_mesaj_db(chat_id, role, content):
    """Salvează un mesaj legat de un anumit chat_id"""
    try:
        supabase.table("chat_history").insert({
             "user_session": USER_ID, # Încă păstrăm asta pentru siguranță/compatibilitate
             "chat_id": chat_id,
             "role": role,
             "content": content
        }).execute()
    except Exception as e:
        print(f"Eroare DB la salvare mesaj: {e}")

def incarca_istoric_db(chat_id):
    """Încarcă mesajele DOAR pentru conversația selectată"""
    if not chat_id: return []
    try:
        response = supabase.table("chat_history").select("role, content").eq("chat_id", chat_id).order("created_at").execute()
        return response.data
    except Exception as e:
        return []

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
        if r.status_code == 200:
            return r.text[:5000]
        return f"Eroare: Nu am putut citi. Cod HTTP: {r.status_code}"
    except Exception as e:
        return f"Eroare: {str(e)}"

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

# --- MANAGEMENTUL STĂRII (SESSION STATE) ---
# Ce chat este activ acum?
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

# Lista de mesaje din interfață pentru chat-ul curent
if "mesaje" not in st.session_state:
    st.session_state.mesaje = []


# ====================================================================
# --- INTERFAȚA LATERALĂ (SIDEBAR) ---
# ====================================================================
with st.sidebar:
    st.header("Conversațiile tale")
    
    # Buton pentru o conversație nouă
    if st.button("➕ Conversație Nouă", use_container_width=True):
        st.session_state.current_chat_id = None # Resetăm selecția
        st.session_state.mesaje = [] # Golem ecranul
        st.rerun() # Reîncărcăm pagina ca să aplicăm
        
    st.divider()
    
    # Afișăm lista cu discuțiile vechi
    lista_conversatii = obtine_lista_conversatii()
    
    for conv in lista_conversatii:
        # Dacă apeși pe un buton din listă...
        if st.button(conv["title"], key=conv["id"], use_container_width=True):
            st.session_state.current_chat_id = conv["id"]
            # Când schimbăm chat-ul, încărcăm mesajele din DB
            st.session_state.mesaje = incarca_istoric_db(conv["id"])
            # Dacă nu are mesaje salvate în DB, punem doar system prompt
            if not st.session_state.mesaje:
                system_prompt = "Ești un asistent tehnic expert."
                st.session_state.mesaje = [{"role": "system", "content": system_prompt}]
                salveaza_mesaj_db(conv["id"], "system", system_prompt)
            st.rerun()

# ====================================================================
# --- ZONA PRINCIPALĂ DE CHAT ---
# ====================================================================

# Dacă suntem într-un chat nou (sau nu am selectat nimic) și ecranul e gol
if st.session_state.current_chat_id is None and not st.session_state.mesaje:
     system_prompt = "Ești un asistent tehnic expert. Răspunde concis."
     st.session_state.mesaje = [{"role": "system", "content": system_prompt}]

# Afișăm istoricul vizual
for msg in st.session_state.mesaje:
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.markdown(content)

# LOGICA PRINCIPALĂ CÂND UTILIZATORUL SCRIE CEVA
if user_input := st.chat_input("Scrie mesajul tău aici..."):
    
    # 1. Dacă nu avem un Chat ID (e prima oară când scriem în acest ecran gol)
    if st.session_state.current_chat_id is None:
        # Creăm "dosarul" în baza de date cu primele 20 de litere din mesaj ca titlu
        titlu_scurt = user_input[:20] + "..." if len(user_input) > 20 else user_input
        noul_id = creeaza_conversatie_noua(titlu=titlu_scurt)
        st.session_state.current_chat_id = noul_id
        
        # Salvăm promptul de sistem care stătea în așteptare în noul chat
        salveaza_mesaj_db(st.session_state.current_chat_id, "system", st.session_state.mesaje[0]["content"])
        
        # Forțăm refresh la meniul lateral (ca să apară noul titlu)
        # folosim un truc cu rerun la final
        needs_rerun = True
    else:
        needs_rerun = False

    # 2. Afișăm pe ecran și salvăm mesajul utilizatorului
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.mesaje.append({"role": "user", "content": user_input})
    salveaza_mesaj_db(st.session_state.current_chat_id, "user", user_input) 
    
    # 3. Răspunsul Asistentului
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
                        rez_live = "Eroare: Această unealtă nu există."
                        
                    st.session_state.mesaje.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": rez_live
                    })
                    
            if not bot_reply:
                bot_reply = "Fișierul a fost citit, dar asistentul nu a formulat o explicație."
                
            placeholder.markdown(bot_reply)
            st.session_state.mesaje.append({"role": "assistant", "content": bot_reply})
            salveaza_mesaj_db(st.session_state.current_chat_id, "assistant", bot_reply)
            
        except Exception as e:
            placeholder.markdown(f"⚠️ Eroare critică la generare: {e}")
            
    # Dacă tocmai am creat un chat nou, facem un scurt refresh 
    # ca să actualizăm lista din stânga cu noul titlu.
    if needs_rerun:
        st.rerun()

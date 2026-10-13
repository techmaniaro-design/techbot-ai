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

# 🌟 Funcție nouă: Actualizarea titlului în baza de date
def actualizeaza_titlu_conversatie(chat_id, noul_titlu):
    try:
        supabase.table("chats").update({"title": noul_titlu}).eq("id", chat_id).execute()
    except Exception as e:
        print(f"Eroare la actualizare titlu: {e}")

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

def sterge_conversatie(chat_id):
    try:
        supabase.table("chat_history").delete().eq("chat_id", chat_id).execute()
        supabase.table("chats").delete().eq("id", chat_id).execute()
    except Exception as e: 
        print(f"Eroare la ștergere: {e}")

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
    st.caption(f"👤 Logat ca: **{st.session_state.user_email if st.session_state.user_email else 'Utilizator'}**")
    
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
        st.session_state.clear()
        js_code = """
        <script>
            document.cookie = "techbot_uid=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            document.cookie = "techbot_email=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            window.parent.location.reload();
        </script>
        """
        components.html(js_code, height=0)
        st.stop()
        
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
        col_titlu, col_sterge = st.columns([0.65, 0.35])
        
        with col_titlu:
            if st.button(conv["title"], key=f"load_{conv['id']}", use_container_width=True):
                st.session_state.current_chat_id = conv["id"]
                st.session_state.fisiere_procesate = []
                st.session_state.mesaje = incarca_istoric_db(conv["id"])
                if not st.session_state.mesaje:
                    prompt = "Ești un asistent tehnic expert."
                    st.session_state.mesaje = [{"role": "system", "content": prompt}]
                    salveaza_mesaj_db(conv["id"], "system", prompt)
                st.rerun()
                
        with col_sterge:
            if st.button("🗑️", key=f"del_{conv['id']}", help="Șterge", use_container_width=True):
                sterge_conversatie(conv["id"])
                if str(st.session_state.current_chat_id) == str(conv["id"]):
                    st.session_state.current_chat_id = None
                    st.session_state.mesaje = []
                    st.session_state.fisiere_procesate = []
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
    
    # 🌟 Găsim un titlu relevant din numele fișierului
    titlu_generat = f"Analiză: {fisier_incarcat.name[:15]}..."
    
    if st.session_state.current_chat_id is None:
        st.session_state.current_chat_id = creeaza_conversatie_noua(titlu=titlu_generat)
        salveaza_mesaj_db(st.session_state.current_chat_id, "system", st.session_state.mesaje[0]["content"])
    
    mesaj_fisier = f"📄 **Am încărcat fișierul:** `{fisier_incarcat.name}`\n\n**Conținut:**\n```\n{text_extras[:10000]}\n```\n\nFolosește aceste date."
    st.session_state.mesaje.append({"role": "user", "content": mesaj_fisier})
    salveaza_mesaj_db(st.session_state.current_chat_id, "user", mesaj_fisier)
    st.session_state.fisiere_procesate.append(fisier_incarcat.name)
    needs_rerun = True

if user_input := st.chat_input("Scrie mesajul tău..."):
    # 🌟 Aici este logica nouă: generăm un titlu la prima interacțiune 
    este_conversatie_noua = False
    if st.session_state.current_chat_id is None:
        este_conversatie_noua = True
        st.session_state.current_chat_id = creeaza_conversatie_noua(titlu="Se generează titlul...")
        salveaza_mesaj_db(st.session_state.current_chat_id, "system", st.session_state.mesaje[0]["content"])
        
        # Generăm titlul în fundal cerând AI-ului un rezumat ultra-scurt
        try:
            prompt_titlu = f"Generează un titlu de maxim 4 cuvinte, descriptiv și în română, pentru această întrebare: '{user_input}'. Oferă DOAR titlul, fără ghilimele sau explicații."
            raspuns_titlu = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt_titlu}],
                max_tokens=10
            )
            titlu_final = raspuns_titlu.choices[0].message.content.strip().replace('"', '')
            if not titlu_final:
                titlu_final = user_input[:20] + "..."
                
            actualizeaza_titlu_conversatie(st.session_state.current_chat_id, titlu_final)
        except Exception:
            actualizeaza_titlu_conversatie(st.session_state.current_chat_id, user_input[:20] + "...")

    with st.chat_message("user"): st.markdown(user_input)
    st.session_state.mesaje.append({"role": "user", "content": user_input})
    salveaza_mesaj_db(st.session_state.current_chat_id, "user", user_input) 
    
    with st.chat_message("assistant"):
        placeholder = st.empty()
        
        try:
            bot_reply = ""
            while True:
                mesaje_de_trimis = [st.session_state.mesaje[0]] + st.session_state.mesaje[-4:] if len(st.session_state.mesaje) > 5 else st.session_state.mesaje
                
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b", 
                    messages=mesaje_de_trimis, 
                    tools=tools, 
                    tool_choice="auto",
                    stream=True 
                )
                
                chunk_reply = ""
                tool_calls_dict = {}
                
                for chunk in response:
                    delta = chunk.choices[0].delta
                    
                    if delta.content:
                        chunk_reply += delta.content
                        placeholder.markdown(chunk_reply + "▌")
                        
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = {
                                    "id": tc_chunk.id, 
                                    "type": "function", 
                                    "function": {"name": tc_chunk.function.name or "", "arguments": tc_chunk.function.arguments or ""}
                                }
                            else:
                                if tc_chunk.function.name:
                                    tool_calls_dict[idx]["function"]["name"] += tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    tool_calls_dict[idx]["function"]["arguments"] += tc_chunk.function.arguments

                if chunk_reply:
                    placeholder.markdown(chunk_reply)
                
                if not tool_calls_dict:
                    bot_reply = chunk_reply
                    break
                
                tool_calls_list = list(tool_calls_dict.values())
                st.session_state.mesaje.append({
                    "role": "assistant",
                    "content": chunk_reply,
                    "tool_calls": tool_calls_list
                })
                
                for tc in tool_calls_list:
                    func_name = tc["function"]["name"]
                    try:
                        argumente = json.loads(tc["function"]["arguments"])
                    except:
                        argumente = {}
                        
                    if func_name == "cauta_pe_internet":
                        query = argumente.get("query", "")
                        placeholder.markdown(f"🔄 **Caut pe net:** `{query}`...")
                        rez_live = cauta_pe_internet(query)
                    elif func_name == "citeste_cod_github":
                        url = argumente.get("url", "")
                        placeholder.markdown(f"💻 **Citesc codul:** `{url}`...")
                        rez_live = citeste_cod_github(url)
                    else: 
                        rez_live = "Eroare: Unealtă inexistentă."
                        
                    st.session_state.mesaje.append({"role": "tool", "tool_call_id": tc["id"], "content": str(rez_live)})
                    
            if not bot_reply or not bot_reply.strip():
                bot_reply = "⚠️ Eroare internă AI: Modelul a returnat un text gol. Te rog trimite mesajul din nou."
                placeholder.markdown(bot_reply)
                
            st.session_state.mesaje.append({"role": "assistant", "content": bot_reply})
            salveaza_mesaj_db(st.session_state.current_chat_id, "assistant", bot_reply)
            
            st.download_button("💾 Salvează Răspunsul", data=bot_reply, file_name=f"raspuns_{len(st.session_state.mesaje)}.txt", key=f"dl_live_{uuid.uuid4().hex[:6]}")
            
            # 🌟 Dacă a fost un chat nou, forțăm o reîncărcare la final pentru a afișa titlul frumos în meniul din stânga!
            if este_conversatie_noua:
                st.rerun()
                
        except Exception as e:
            placeholder.markdown(f"⚠️ Eroare critică la generare: S-a atins limita serverului sau ai picat netul.")
            
if needs_rerun: st.rerun()

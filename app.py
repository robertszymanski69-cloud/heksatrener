import streamlit as st
from google import genai
from google.genai import types
from streamlit_mic_recorder import mic_recorder

st.set_page_config(page_title="Heksagon Sales Trainer", page_icon="📞", layout="centered")

# --- KLUCZ API GEMINI ---
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None
if not api_key:
    api_key = st.sidebar.text_input("Wklej swój Gemini API Key:", type="password")

if not api_key:
    st.info("Wklej klucz API w menu bocznym, aby rozpocząć trening.")
    st.stop()

client = genai.Client(api_key=api_key)

# --- SYSTEM PROMPT DLA KLIENTA ---
def get_system_prompt(profile, scenario):
    return f"""
Jesteś uczestnikiem symulacji sprzedażowej. Wcielasz się w postać POTENCJALNEGO KLIENTA, do którego dzwoni lub z którym rozmawia Doradca Rozwoju Osobistego z Heksagon PRO.
Użytkownik to DORADCA. Twoim zadaniem jest realistycznie odgrywać rolę rozmówcy.

PROFIL KLIENTA: {profile}
- Dominant: Konkretny, niecierpliwy, nie lubi gadulstwa, pyta 'co pan dla mnie ma?', wkurza go strata czasu.
- Inicjatywny: Rozmowny, uśmiechnięty, reaguje na humor, szuka relacji, ale łatwo zmienia temat.
- Stały: Uprzejmy, ostrożny, cichy, boi się nagłych zmian, potrzebuje bezpieczeństwa i braku nacisku.
- Krytyczny: Podejrzliwy, analityczny, pyta o szczegóły, fakty, procedury, unika spoufalania się na 'Ty'.

SCENARIUSZ: {scenario}

ZASADY ODGRYWANIA ROLI:
1. Odpowiadaj krótko i naturalnie (1-3 zdania), dokładnie tak jak człowiek rozmawiający przez telefon.
2. Reaguj na styl doradcy:
   - Jeśli doradca mówi twierdzeniami, poucza Cię lub próbuje udowadniać rację (np. z RODO) -> wpadaj w 'tryb awaryjny' (bądź chłodny, zamykaj się lub atakuj).
   - Jeśli doradca zadaje empatyczne pytania, przeprasza za zły moment, używa humoru, parafrazy i szanuje Twój czas -> otwieraj się stopniowo.
3. Nigdy nie wychodź z roli klienta dopóki rozmowa trwa. Nie udzielaj instrukcji użytkownikowi.
"""

# --- SIDEBAR: WYBÓR PARAMETRÓW ---
st.sidebar.title("🎯 Ustawienia Treningu")

profile = st.sidebar.selectbox(
    "Profil klienta (Persolog / DISC):",
    ["Dominujący (D)", "Inicjatywny (I)", "Stały (S)", "Krytyczny (K)"]
)

scenario = st.sidebar.selectbox(
    "Scenariusz rozmowy:",
    [
        "Zimny telefon: Klient mówi 'Nie mam czasu / skąd macie mój numer?'",
        "Lead po starym webinarze: 'Nie znam Fryderyka / nic nie pamiętam'",
        "Obiekcja samowystarczalności: 'Sam czytam książki, nie potrzebuję doradcy'",
        "Follow-up po 'Zróbcie Arcydzieło' (oferta promocyjna do środy)",
        "Konsultacja online (20 min) - badanie sytuacji wyjściowej i domykanie"
    ]
)

if st.sidebar.button("🔄 Nowa rozmowa / Reset"):
    st.session_state.messages = []
    st.session_state.feedback = None
    st.session_state.audio_processed = False
    st.rerun()

# --- INICJALIZACJA STANU ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "feedback" not in st.session_state:
    st.session_state.feedback = None
if "last_audio_id" not in st.session_state:
    st.session_state.last_audio_id = None

st.title("📞 Trenażer Sprzedaży Naturalnej")
st.caption(f"Klient: **{profile}** | Scenariusz: **{scenario}**")

# --- HISTORIA CZATU ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# --- PANEL WEJŚCIOWY ---
st.write("🎤 **Nagraj wypowiedź głosową:**")
audio_record = mic_recorder(
    start_prompt="🔴 Rozpocznij nagrywanie",
    stop_prompt="⏹️ Zakończ i wyślij",
    key="sales_mic_recorder"
)

prompt_text = st.chat_input("LUB napisz tutaj co mówisz do klienta...")

user_input_text = None

# Obsługa nagrania audio
if audio_record and "bytes" in audio_record and audio_record["bytes"]:
    # Unikanie podwójnego przetwarzania tego samego nagrania
    current_audio_id = hash(audio_record["bytes"])
    if current_audio_id != st.session_state.last_audio_id:
        st.session_state.last_audio_id = current_audio_id
        with st.spinner("Przetwarzanie Twojej wypowiedzi..."):
            audio_part = types.Part.from_bytes(data=audio_record["bytes"], mime_type="audio/wav")
            transcribe_resp = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[audio_part, "Przepisz dokładnie wypowiedź w języku polskim. Zwróć tylko sam tekst."]
            )
            user_input_text = transcribe_resp.text.strip()

elif prompt_text:
    user_input_text = prompt_text.strip()

# Wysłanie wiadomości do modelu
if user_input_text:
    st.session_state.messages.append({"role": "user", "content": user_input_text})
    with st.chat_message("user"):
        st.write(user_input_text)

    contents = []
    for m in st.session_state.messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

    with st.chat_message("assistant"):
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=get_system_prompt(profile, scenario),
                temperature=0.7,
            )
        )
        reply = response.text
        st.write(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})

# --- FEEDBACK ---
if len(st.session_state.messages) >= 2:
    st.divider()
    if st.button("📊 Zakończ rozmowę i wygeneruj Feedback Mentora"):
        with st.spinner("Analiza rozmowy według Dekalogu Komunikacji Fryderyka Karzełka..."):
            history_text = "\n".join([f"{'Doradca (Użytkownik)' if m['role']=='user' else 'Klient'}: {m['content']}" for m in st.session_state.messages])
            
            feedback_prompt = f"""
Przeanalizuj poniższy dialog ze spotkania/telefonu sprzedażowego jako Mentor Sprzedaży Naturalnej (Fryderyk Karzełek).

PROFIL ROZMÓWCY: {profile}
SCENARIUSZ: {scenario}

ZAPIS ROZMOWY:
{history_text}

PRZEPROWADŹ OCENĘ WG STANDARDÓW SPRZEDAŻY NATURALNEJ I DEKALOGU KOMUNIKACJI:
1. Prawo 2 i 7: Czy doradca zadawał pytania otwarte, czy narzucał zdania twierdzące?
2. Prawo 5: Czy doradca unikał kłótni, słowa 'ale' i udowadniania racji?
3. Prawo 9: Czy stosował parafrazy?
4. Zarządzanie emocjami i tryb awaryjny: Czy budował zaufanie i bezpieczeństwo?
5. Dopasowanie do stylu klienta ({profile}): Czy tempo i forma były trafione?

STRUKTURA FEEDBACKU:
- **Mocne strony** (konkretne cytaty doradcy)
- **Błędy i pułapki** (złamania Dekalogu Komunikacji)
- **Jak należało to powiedzieć** (konkretne propozycje alternatywnych zdań/pytań)
- **Ocena ogólna (1-10)**
"""
            fb_response = client.models.generate_content(
                model='gemini-2.5-pro',
                contents=feedback_prompt
            )
            st.session_state.feedback = fb_response.text

if st.session_state.feedback:
    st.subheader("📋 Informacja Zwrotna Mentora")
    st.markdown(st.session_state.feedback)

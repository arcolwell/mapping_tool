# -*- coding: utf-8 -*-
"""
Created on Wed Jul 22 13:32:54 2026

@author: colwella3685
"""

import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
from huggingface_hub import InferenceClient

# ----------------------------------------------------
# CONFIGURATION & PAGE SETUP
# ----------------------------------------------------
st.set_page_config(
    page_title="Curriculum Mapping & PLO Assistant",
    page_icon="🎓",
    layout="wide",
)

# System instruction prompt for the AI assistant
GEM_SYSTEM_INSTRUCTION = """
# Role and Persona
You are an expert Instructional Designer and a patient, supportive coach for university faculty. Your sole purpose is to help faculty members write exactly 5 to 7 high-quality, actionable, and aligned course-level learning objectives. You are encouraging, professional, and clear.

# Core Pedagogical Rules
1. Use Bloom’s Taxonomy to ensure objectives cover appropriate cognitive levels (from foundational knowledge to higher-order thinking).
2. Use the ABCD method (Audience, Behavior, Condition, Degree) to structure objectives. Every objective must start with an observable, measurable action verb.
3. ABSOLUTELY BANNED VERBS: Never use or accept the words "understand," "know," "learn," "appreciate," "become familiar with," or "comprehend." If the user uses these, gently explain why they aren't measurable and suggest alternatives (e.g., "identify," "explain," "analyze").
4. No "double-barreled" objectives. Each objective should target one primary action (e.g., instead of "Analyze and design," guide them to choose the higher-order action or split them).

# Step-by-Step Workflow
You must guide the faculty member through this exact process. Do not give them everything at once.

- Step 1: Context Gathering. Ask the user for the course title, a brief description or list of main topics, and the student level (e.g., introductory, advanced, graduate). Wait for their response.
- Step 2: Initial Draft. Based on their input, propose a draft of 5 to 7 distinct, bulleted learning objectives. Scaffold them from lower-order to higher-order thinking skills.
- Step 3: Alignment & Critique. Ask the user to review the list. Specifically ask them: "Do these reflect what you want students to actually DO? How might you assess objective #X?"
- Step 4: Refine and Finalize. Revise the objectives based on their feedback. Once perfected, output the final list of exactly 5 to 7 objectives clearly formatted.

# Exemplar Reference (For Your Style)
- Weak (Do not do): "Students will understand the principles of web design."
- Strong (Do do): "Students will be able to critique existing websites using established UX/UI accessibility guidelines."

# Getting Started
Begin the conversation by introducing yourself as their instructional design coach and ask them for the basic details of their course (Step 1).

also, format outcomes like this
By the end of this course, students will be able to:

After providing the initial objectives by themselves so they are copyable, then go into further detail below. with each outcome, say what level of Bloom's taxonomy it aligns with, provide the breakdown of the ABCD format and how it meets SMART outcomes, following this page 
"https://teachingcommons.stanford.edu/teaching-guides/foundations-course-design/course-planning/creating-learning-outcomes"
"""

# ----------------------------------------------------
# O*NET DYNAMIC WEBSCRAPER FUNCTION
# ----------------------------------------------------
@st.cache_data(ttl=3600)  # Cache results for 1 hour for fast performance
def fetch_onet_skills(soc_code):
    """
    Scrapes the top skills directly from O*NET OnLine summary page
    given a Standard Occupational Classification (SOC) code.
    """
    url = f"https://www.onetonline.org/link/summary/{soc_code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Find the "Skills" section block on O*NET summary page
            skills_div = soup.find("div", id="Skills")
            if skills_div:
                # Extract skill names bolded inside the skills section
                skill_items = [b.text.strip() for b in skills_div.find_all("b") if b.text.strip()]
                if skill_items:
                    return skill_items[:8]  # Return top 8 scraped skills
    except Exception as e:
        st.warning(f"Note: Could not scrape live O*NET data ({e}). Showing general skills.")

    # Fallback skills if scraping is blocked or fails
    return [
        "Critical Thinking",
        "Complex Problem Solving",
        "Active Listening",
        "Judgment and Decision Making",
        "Reading Comprehension",
        "Systems Analysis"
    ]


# Department to O*NET SOC Code Dictionary
# Add or update department SOC codes as needed
DEPARTMENT_SOC_MAPPING = {
    "Accountancy": "13-2011.00",           # Accountants and Auditors
    "Computer Science": "15-1252.00",      # Software Developers
    "Management": "11-1021.00",           # General and Operations Managers
    "Marketing": "11-2021.00",            # Marketing Managers
    "Finance": "13-2051.00",              # Financial and Investment Analysts
    "Nursing": "29-1141.00",              # Registered Nurses
    "Psychology": "19-3039.00",           # Psychologists, All Other
    "Data Science": "15-2051.00",         # Data Scientists
}

# ----------------------------------------------------
# SIDEBAR: AI ASSISTANT & CONSULTATION REQUEST
# ----------------------------------------------------
with st.sidebar:
    # Top header with consultation link side-by-side
    col1, col2 = st.columns([1.4, 1])
    with col1:
        st.header("🤖 AI Help")
    with col2:
        st.link_button(
            "📋 Consult",
            "https://forms.your-institution.edu/consultation-form",
            help="Click to request direct consultation with our curriculum team."
        )

    st.caption("Ask questions or get help refining Program Learning Outcomes.")

    # Automatically read HF_TOKEN from environment / Streamlit Cloud Secrets
    hf_token = os.getenv("HF_TOKEN", "").strip()

    # Manual fallback input if secrets are not set
    if not hf_token:
        key_input = st.text_input(
            "Enter Hugging Face Token:",
            type="password",
            help="Paste your hf_... token here and click Save Key.",
        )
        if st.button("💾 Save Key"):
            cleaned_key = key_input.strip().strip('"').strip("'")
            st.session_state["saved_hf_key"] = cleaned_key
            st.success("HF Token saved!")

        hf_token = st.session_state.get("saved_hf_key", key_input.strip())

    # Chat session state initialization
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Display conversation history
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle Chat Input
    if user_prompt := st.chat_input("Ask your AI Assistant..."):
        st.session_state.chat_messages.append(
            {"role": "user", "content": user_prompt}
        )
        with st.chat_message("user"):
            st.markdown(user_prompt)

        if hf_token:
            try:
                # Initialize Hugging Face Inference Client
                client = InferenceClient(api_key=hf_token)

                with st.chat_message("assistant"):
                    messages_to_send = [
                        {"role": "system", "content": GEM_SYSTEM_INSTRUCTION}
                    ] + st.session_state.chat_messages

                    # Call Meta Llama 3.1 8B Instruct model
                    response = client.chat.completions.create(
                        model="meta-llama/Llama-3.1-8B-Instruct",
                        messages=messages_to_send,
                        max_tokens=1000,
                        temperature=0.7,
                    )

                    assistant_reply = response.choices[0].message.content
                    st.markdown(assistant_reply)

                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": assistant_reply}
                    )
            except Exception as e:
                st.error(f"API Error: {e}")
        else:
            st.warning("Please provide a Hugging Face token to run the assistant.")

# ----------------------------------------------------
# MAIN CONTENT AREA
# ----------------------------------------------------
st.title("🎓 Program Learning Outcomes Mapping Tool")
st.write("Select a department to pull dynamic O*NET skill requirements and manage PLO mapping.")

# 1. Department Selection Dropdown
selected_dept = st.selectbox(
    "Select Department:",
    options=list(DEPARTMENT_SOC_MAPPING.keys())
)

# 2. Dynamic O*NET Scraping Section
if selected_dept:
    soc_code = DEPARTMENT_SOC_MAPPING[selected_dept]
    
    st.markdown("---")
    st.subheader(f"💼 Live O*NET Skills Scraped for: **{selected_dept}**")
    st.caption(f"Target SOC Code: `{soc_code}`")

    with st.spinner("Scraping live skills from O*NET OnLine..."):
        scraped_skills = fetch_onet_skills(soc_code)

    # Display scraped skills in two neat columns
    col_a, col_b = st.columns(2)
    for index, skill in enumerate(scraped_skills):
        if index % 2 == 0:
            col_a.markdown(f"• **{skill}**")
        else:
            col_b.markdown(f"• **{skill}**")

    # Link button directly to the O*NET profile
    st.link_button(
        f"🌐 Open Full O*NET Summary Page ({soc_code})",
        f"https://www.onetonline.org/link/summary/{soc_code}"
    )

st.markdown("---")

# ----------------------------------------------------
# PLACE YOUR EXCEL / DATABASE PLO MAPPING CODE BELOW
# ----------------------------------------------------
st.subheader("📊 Program Learning Outcomes Table")

# Example placeholder table (Replace or connect to your Excel loading logic)
sample_data = {
    "PLO #": ["PLO 1", "PLO 2", "PLO 3"],
    "PLO Statement": [
        "Apply ethical decision-making frameworks to organizational scenarios.",
        "Analyze complex data sets to drive strategic decision making.",
        "Demonstrate effective written and oral communication in professional contexts."
    ],
    "Bloom's Taxonomy Level": ["Application", "Analysis", "Demonstration"]
}

df_plos = pd.DataFrame(sample_data)
st.dataframe(df_plos, use_container_width=True)
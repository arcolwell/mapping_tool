# -*- coding: utf-8 -*-
"""
Created on Wed Jul 22 13:56:39 2026

@author: colwella3685
"""

import datetime
import os
import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st
from huggingface_hub import InferenceClient

# ----------------------------------------------------
# FILE & DATABASE CONFIGURATION
# ----------------------------------------------------
EXCEL_PATH = "program learning outcomes list.xlsx"
DB_PATH = "plo_mapping_test4_db.db"

# System instruction prompt for the AI assistant
GEM_SYSTEM_INSTRUCTION = """
You are an expert higher education curriculum mapping assistant. 
Your goal is to help faculty, department heads, and curriculum designers write, 
refine, and align Program Learning Outcomes (PLOs) using Bloom's Taxonomy 
and industry skill frameworks like O*NET.
"""

# ----------------------------------------------------
# DATABASE FUNCTIONS
# ----------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mapping_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                program TEXT NOT NULL,
                outcome_index INTEGER NOT NULL DEFAULT 1,
                course TEXT NOT NULL,
                outcome TEXT NOT NULL,
                is_mapped BOOLEAN NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )


def save_mapping_to_db(program_name, mapping_df):
    # Add explicit index to preserve outcome position over edits
    df_to_save = mapping_df.copy()
    df_to_save["outcome_index"] = range(1, len(df_to_save) + 1)

    tall_df = df_to_save.melt(
        id_vars=["outcome_index", "Program Learning Outcomes"],
        var_name="course",
        value_name="is_mapped",
    )
    tall_df.rename(
        columns={"Program Learning Outcomes": "outcome"}, inplace=True
    )
    tall_df["program"] = program_name
    tall_df["submitted_at"] = datetime.datetime.now()

    records_to_insert = tall_df[
        [
            "program",
            "outcome_index",
            "course",
            "outcome",
            "is_mapped",
            "submitted_at",
        ]
    ]

    with get_db_connection() as conn:
        records_to_insert.to_sql(
            "mapping_submissions", conn, if_exists="append", index=False
        )


def get_program_history_by_index(program_name):
    try:
        with get_db_connection() as conn:
            query = """
                SELECT outcome_index, outcome, course, is_mapped, submitted_at
                FROM mapping_submissions 
                WHERE program = ? 
                ORDER BY submitted_at DESC
            """
            return pd.read_sql_query(query, conn, params=(program_name,))
    except Exception:
        return pd.DataFrame()


init_db()

# ----------------------------------------------------
# HELPER FUNCTIONS & O*NET SCRAPER
# ----------------------------------------------------
def load_program_outcomes(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"Could not find the Excel file at {file_path}"
        )

    if file_path.endswith(".xlsx") or file_path.endswith(".xls"):
        df = pd.read_excel(file_path)
    elif file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        raise ValueError("Unsupported file format.")

    df.columns = df.columns.str.strip()
    if not {"Program", "Outcome"}.issubset(df.columns):
        raise KeyError(
            "Spreadsheet must contain 'Program' and 'Outcome' columns."
        )

    df["Program"] = df["Program"].astype(str).str.strip()
    df["Outcome"] = df["Outcome"].astype(str).str.strip()
    df = df.dropna(subset=["Program", "Outcome"])

    return df.groupby("Program")["Outcome"].apply(list).to_dict()


def get_program_abbreviation(program_name):
    words = program_name.replace("/", " ").replace("-", " ").split()
    if len(words) >= 2:
        return "".join([w[0].upper() for w in words[:3]])
    elif len(words) == 1:
        return words[0][:3].upper()
    return "CRS"


def get_department_course_bundle(program_name):
    prefix = get_program_abbreviation(program_name)
    return [
        f"{prefix} 101",
        f"{prefix} 201",
        f"{prefix} 301",
        f"{prefix} 401",
        f"{prefix} Capstone",
    ]


OTHER_COURSES_CATALOG = [
    "MATH 105 - Statistics",
    "ENG 101 - Composition",
    "COMM 110 - Public Speaking",
    "BUS 200 - Professional Ethics",
    "DATA 210 - Data Literacy",
]


@st.cache_data(ttl=86400)
def search_onet_soc_code(program_name):
    """
    Searches O*NET OnLine for the most relevant SOC code when a 
    program isn't found in the standard keyword dictionary.
    """
    url = f"https://www.onetonline.org/find/result?q={requests.utils.quote(program_name)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.find_all("a", href=True):
                if "/link/summary/" in link["href"]:
                    soc = link["href"].split("/link/summary/")[1]
                    if len(soc) >= 8 and "-" in soc:
                        return soc
    except Exception:
        pass
    return "11-1021.00"  # Default fallback if dynamic search encounters an issue


@st.cache_data(ttl=3600)
def fetch_onet_skills(soc_code):
    """Dynamically fetches top skills directly from O*NET OnLine summary page."""
    url = f"https://www.onetonline.org/link/summary/{soc_code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            skills_div = soup.find("div", id="Skills")
            if skills_div:
                skill_items = [
                    b.text.strip() for b in skills_div.find_all("b") if b.text.strip()
                ]
                if skill_items:
                    return skill_items[:8]
    except Exception:
        pass

    return [
        "Critical Thinking",
        "Complex Problem Solving",
        "Active Listening",
        "Judgment and Decision Making",
        "Systems Analysis",
    ]


# ----------------------------------------------------
# MAIN APP
# ----------------------------------------------------
def main():
    st.set_page_config(
        page_title="Program Outcome Mapping Tool",
        page_icon="🎓",
        layout="wide",
    )

    # ----------------------------------------------------
    # SIDEBAR: AI ASSISTANT & CONSULTATION REQUEST
    # ----------------------------------------------------
    with st.sidebar:
        col1, col2 = st.columns([1.4, 1])
        with col1:
            st.header("🤖 AI Help")
        with col2:
            st.link_button(
                "📋 Request Consultation",
                "https://forms.your-institution.edu/consultation-form",
                help="Click to request direct consultation with our curriculum team.",
            )

        st.caption("Ask questions or get help refining Program Learning Outcomes.")

        # Read HF_TOKEN automatically from Streamlit Secrets or environment
        hf_token = os.getenv("HF_TOKEN", "").strip()

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

        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if user_prompt := st.chat_input("Ask your AI Assistant..."):
            st.session_state.chat_messages.append(
                {"role": "user", "content": user_prompt}
            )
            with st.chat_message("user"):
                st.markdown(user_prompt)

            if hf_token:
                try:
                    client = InferenceClient(api_key=hf_token)

                    with st.chat_message("assistant"):
                        messages_to_send = [
                            {"role": "system", "content": GEM_SYSTEM_INSTRUCTION}
                        ] + st.session_state.chat_messages

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
    # MAIN PAGE HEADER & PROGRAM SELECTION
    # ----------------------------------------------------
    st.title("🎓 Program Outcome Mapping Tool")
    st.info(f"🧪 Database Target: `{DB_PATH}`")
    st.markdown("---")

    # Load Excel Data
    if "programs" not in st.session_state:
        try:
            st.session_state.programs = load_program_outcomes(EXCEL_PATH)
            st.session_state.load_error = None
        except Exception as e:
            st.session_state.programs = {}
            st.session_state.load_error = str(e)

    if st.session_state.load_error:
        st.error(
            f"❌ Error loading Excel data: {st.session_state.load_error}"
        )
        return

    program_list = sorted(list(st.session_state.programs.keys()))
    selected_program = st.selectbox(
        "Select your Department / Program:", program_list
    )

    if selected_program:
        # ----------------------------------------------------
        # DYNAMIC O*NET SOC LOOKUP SYSTEM
        # ----------------------------------------------------
        SOC_KEYWORDS = {
            # Business, Accounting & Finance
            "account": "13-2011.00",      # Accountants and Auditors
            "audit": "13-2011.00",
            "finance": "13-2051.00",      # Financial Analysts
            "fintech": "13-2051.00",
            "market": "11-2021.00",       # Marketing Managers
            "advert": "11-2021.00",
            "manag": "11-1021.00",        # General Managers
            "admin": "11-1021.00",
            "busin": "11-1021.00",
            "exec": "11-1011.00",
            "supply": "13-1081.00",       # Logistics / Supply Chain
            "logist": "13-1081.00",
            "human resource": "13-1071.00", # HR Specialists
            "hr": "13-1071.00",
            "entrepreneur": "11-1021.00",

            # Computer Science & Technology
            "comput": "15-1252.00",       # Software Developers
            "software": "15-1252.00",
            "data science": "15-2051.00",  # Data Scientists
            "analytics": "15-2051.00",
            "cyber": "15-1212.00",        # Information Security Analysts
            "security": "15-1212.00",
            "network": "15-1244.00",      # Network Administrators
            "web": "15-1254.00",          # Web Developers
            "information tech": "15-1299.00", # IT Professionals
            "it": "15-1299.00",

            # Engineering & Architecture
            "civil": "17-2051.00",        # Civil Engineers
            "mechanic": "17-2141.00",     # Mechanical Engineers
            "electric": "17-2071.00",     # Electrical Engineers
            "biomed": "17-2031.00",       # Bioengineers
            "engin": "17-2199.00",        # Engineers, General
            "architect": "17-1011.00",    # Architects

            # Health & Medicine
            "nurs": "29-1141.00",         # Registered Nurses
            "pharm": "29-1051.00",        # Pharmacists
            "physician": "29-1210.00",    # Physicians
            "public health": "11-9111.00",# Medical/Health Managers
            "health": "11-9111.00",
            "kinesio": "29-1128.00",      # Exercise Physiologists
            "athletic": "29-9091.00",
            "dental": "29-1021.00",
            "therap": "29-1122.00",       # Occupational Therapists

            # Physical & Life Sciences
            "biology": "19-1029.00",      # Biological Scientists
            "bio": "19-1029.00",
            "chem": "19-2031.00",         # Chemists
            "physic": "19-2012.00",       # Physicists
            "envir": "19-2041.00",        # Environmental Scientists
            "geol": "19-2042.00",         # Geoscientists
            "agri": "19-1011.00",         # Agricultural Scientists

            # Social Sciences & Humanities
            "psych": "19-3039.00",        # Psychologists
            "sociol": "19-3041.00",       # Sociologists
            "crimin": "33-3051.00",       # Police/Criminal Justice
            "justice": "33-3051.00",
            "political": "19-3094.00",    # Political Scientists
            "history": "19-3093.00",      # Historians
            "anthrop": "19-3011.00",      # Anthropologists
            "econom": "19-3011.00",       # Economists
            "social work": "21-1029.00",  # Social Workers

            # Communication, Arts & Design
            "comm": "27-3031.00",         # Public Relations
            "journal": "27-3023.00",      # News Analysts / Reporters
            "media": "27-3041.00",        # Editors / Media
            "graphic": "27-1024.00",      # Graphic Designers
            "design": "27-1024.00",
            "art": "27-1011.00",          # Art Professionals
            "music": "27-2042.00",        # Musicians
            "theater": "27-2011.00",      # Actors/Producers
            "film": "27-2012.00",

            # Education & Math
            "math": "15-2090.00",         # Mathematical Science
            "stat": "15-2041.00",         # Statisticians
            "educat": "25-2031.00",       # Secondary Teachers
            "teach": "25-2031.00",
            "instruction": "25-9031.00",  # Instructional Coordinators
        }

        selected_lower = selected_program.lower()
        soc_code = None

        # Step 1: Check standard keyword dictionary
        for kw, code in SOC_KEYWORDS.items():
            if kw in selected_lower:
                soc_code = code
                break

        # Step 2: Fallback to live web search if program name isn't matched
        if not soc_code:
            with st.spinner(f"Finding best O*NET occupation match for '{selected_program}'..."):
                soc_code = search_onet_soc_code(selected_program)

        # ----------------------------------------------------
        # O*NET DISPLAY EXPANDER
        # ----------------------------------------------------
        with st.expander(f"💼 View Scraped O*NET Skills for {selected_program}", expanded=False):
            custom_soc = st.text_input(
                "O*NET SOC Code (auto-detected, edit if needed):", 
                value=soc_code,
                help="You can manually override the SOC code here if desired."
            )
            
            st.caption(f"Scraped directly from O*NET OnLine (SOC Code: `{custom_soc}`):")
            scraped_skills = fetch_onet_skills(custom_soc)
            
            c_a, c_b = st.columns(2)
            for idx_s, skill_name in enumerate(scraped_skills):
                if idx_s % 2 == 0:
                    c_a.markdown(f"• **{skill_name}**")
                else:
                    c_b.markdown(f"• **{skill_name}**")
                    
            st.link_button(
                f"🌐 Open Full O*NET Summary Page ({custom_soc})",
                f"https://www.onetonline.org/link/summary/{custom_soc}"
            )

        st.markdown("---")

        real_outcomes = st.session_state.programs.get(selected_program, [])
        numbered_outcomes = [
            f"{i+1}. {outcome}" for i, outcome in enumerate(real_outcomes)
        ]

        # ----------------------------------------------------
        # COURSE SELECTION
        # ----------------------------------------------------
        st.subheader("📚 Select Courses to Include in Your Grid")
        dept_bundle = get_department_course_bundle(selected_program)

        col1, col2 = st.columns(2)
        with col1:
            selected_bundle_courses = st.multiselect(
                f"Department Course Bundle ({selected_program}):",
                options=dept_bundle,
                default=dept_bundle[:3],
            )
        with col2:
            selected_extra_courses = st.multiselect(
                "Add Extra / Interdisciplinary Courses:",
                options=OTHER_COURSES_CATALOG,
                default=[],
            )

        custom_course = st.text_input(
            "Or add a custom course/activity name manually:"
        )

        active_courses = (
            selected_bundle_courses + selected_extra_courses
        )
        if custom_course and custom_course.strip():
            active_courses.append(custom_course.strip())

        active_courses = list(dict.fromkeys(active_courses))
        st.markdown("---")

        # ----------------------------------------------------
        # INTERACTIVE GRID (WITH PINNED COLUMN)
        # ----------------------------------------------------
        st.subheader(f"📊 Mapping Grid for {selected_program}")
        st.caption(
            "📌 **Tip:** The outcomes column is frozen on the left. Scroll horizontally to map courses across your curriculum."
        )

        grid_data = {"Program Learning Outcomes": numbered_outcomes}
        for course in active_courses:
            grid_data[course] = [False] * len(numbered_outcomes)

        current_df = pd.DataFrame(grid_data)

        config = {
            "Program Learning Outcomes": st.column_config.TextColumn(
                label="Program Learning Outcomes",
                width=800,
                required=True,
                pinned=True,  # Freezes outcome column on scroll
            )
        }
        for col in active_courses:
            config[col] = st.column_config.CheckboxColumn(
                label=col, default=False, width="small"
            )

        edited_df = st.data_editor(
            current_df,
            num_rows="dynamic",
            column_config=config,
            use_container_width=True,
            row_height=100,
            key=f"editor_{selected_program}_{len(active_courses)}",
        )

        st.markdown("---")

        # ----------------------------------------------------
        # REVIEW OUTCOMES, DOWNLOAD & FULL TEXT EDIT HISTORY
        # ----------------------------------------------------
        st.subheader("📖 Review Outcomes & Change History")

        current_outcomes_df = edited_df[
            ["Program Learning Outcomes"]
        ].dropna()

        # Download Current Outcomes File Button
        outcomes_csv = current_outcomes_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Current Outcomes List (CSV)",
            data=outcomes_csv,
            file_name=f"{selected_program}_Current_Outcomes_{datetime.date.today()}.csv",
            mime="text/csv",
        )

        st.write("##")

        # Fetch DB history for this program
        history_df = get_program_history_by_index(selected_program)

        current_outcomes_list = current_outcomes_df[
            "Program Learning Outcomes"
        ].tolist()

        for idx, outcome_text in enumerate(current_outcomes_list, 1):
            outcome_clean = str(outcome_text).strip()

            with st.container():
                c1, c2 = st.columns([3, 1])

                with c1:
                    st.markdown(f"### Outcome #{idx}")
                    st.write(f"**Current Wording:** {outcome_clean}")

                with c2:
                    if not history_df.empty:
                        matched_history = history_df[
                            history_df["outcome_index"] == idx
                        ]
                    else:
                        matched_history = pd.DataFrame()

                    timestamps = (
                        matched_history["submitted_at"].unique()
                        if not matched_history.empty
                        else []
                    )

                    with st.expander(f"📜 View Text History ({len(timestamps)})"):
                        if not matched_history.empty:
                            grouped = matched_history.groupby("submitted_at")
                            for timestamp, group in grouped:
                                past_text = group["outcome"].iloc[0]
                                mapped_courses = group[
                                    group["is_mapped"] == True
                                ]["course"].tolist()

                                st.markdown(f"🕒 **Saved On:** `{timestamp}`")
                                st.markdown(
                                    f"📝 **Full Text Version:**\n> {past_text}"
                                )

                                if mapped_courses:
                                    st.markdown(
                                        f"🔗 **Mapped Courses:** {', '.join(mapped_courses)}"
                                    )
                                else:
                                    st.markdown(
                                        "🔗 *No courses mapped in this version.*"
                                    )
                                st.divider()
                        else:
                            st.caption(
                                "No prior database submissions found for this outcome position."
                            )

                st.markdown("---")

        # ----------------------------------------------------
        # SUBMIT BUTTON
        # ----------------------------------------------------
        if st.button("🚀 Submit Final Mapping", type="primary"):
            try:
                save_mapping_to_db(selected_program, edited_df)
                st.success(
                    f"Successfully saved curriculum mapping for **{selected_program}** to `{DB_PATH}`!"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save to database: {e}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Created on Mon Sep 28 08:06:11 2026

@author: colwella3685
"""

import datetime
import os
import sqlite3
import pandas as pd
import streamlit as st

# ----------------------------------------------------
# FILE & DATABASE CONFIGURATION
# ----------------------------------------------------
EXCEL_PATH = "program learning outcomes list.xlsx"
DB_PATH = "plo_mapping_test4_db.db"

# Department to O*NET SOC Code Dictionary
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
                mapping_level TEXT NOT NULL DEFAULT 'N/A',
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        try:
            conn.execute(
                "ALTER TABLE mapping_submissions ADD COLUMN mapping_level TEXT NOT NULL DEFAULT 'N/A'"
            )
        except sqlite3.OperationalError:
            pass


def save_mapping_to_db(program_name, mapping_df):
    df_to_save = mapping_df.copy()
    df_to_save["outcome_index"] = range(1, len(df_to_save) + 1)

    tall_df = df_to_save.melt(
        id_vars=["outcome_index", "Program Learning Outcomes"],
        var_name="course",
        value_name="mapping_level",
    )
    tall_df.rename(
        columns={"Program Learning Outcomes": "outcome"}, inplace=True
    )
    tall_df["program"] = program_name
    tall_df["submitted_at"] = datetime.datetime.now()
    
    # Recognizes "N/A" or empty string as unmapped
    tall_df["is_mapped"] = tall_df["mapping_level"].apply(
        lambda lvl: str(lvl).strip() not in ("", "N/A", "Not Mapped")
    )

    records_to_insert = tall_df[
        [
            "program",
            "outcome_index",
            "course",
            "outcome",
            "is_mapped",
            "mapping_level",
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
                SELECT outcome_index, outcome, course, is_mapped, mapping_level, submitted_at
                FROM mapping_submissions 
                WHERE program = ? 
                ORDER BY submitted_at DESC
            """
            return pd.read_sql_query(query, conn, params=(program_name,))
    except Exception:
        return pd.DataFrame()


init_db()

# ----------------------------------------------------
# HELPER FUNCTIONS
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


def get_onet_soc_code(program_name):
    selected_lower = program_name.lower()
    for kw, code in SOC_KEYWORDS.items():
        if kw in selected_lower:
            return code
    return "11-1021.00"  # Default fallback code if not matched in keyword dictionary


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
    # SIDEBAR: GOOGLE GEM LINK & CONSULTATION
    # ----------------------------------------------------
    with st.sidebar:
        st.header("🤖 AI Instructional Design Coach")
        
        st.info(
            "**Enterprise AI Integration Goal:**\n\n"
            "Faculty click below to open our enterprise **Google Gem**, pre-configured with our instructional design system prompt."
        )
        
        # Replace URL with your actual Google Gem link when available
        st.link_button(
            "✨ Launch ID Coach (Google Gem)",
            "https://gemini.google.com/",
            type="primary",
            help="Opens our enterprise Google Gem in a new browser tab."
        )
        
        st.markdown("---")
        
        st.link_button(
            "📋 Request Consultation",
            "https://forms.your-institution.edu/consultation-form",
            help="Click to request direct consultation with our curriculum team.",
        )

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
        # O*NET INDUSTRY SKILLS REFERENCE LINK (NO SCRAPING)
        # ----------------------------------------------------
        soc_code = get_onet_soc_code(selected_program)
        onet_url = f"https://www.onetonline.org/link/summary/{soc_code}"

        st.info(
            f"💡 **Industry Benchmark Reference:** While rethinking outcomes for **{selected_program}**, "
            f"review the top skills, knowledge requirements, and daily tasks listed on O*NET for this field."
        )

        st.link_button(
            f"🌐 Open O*NET Summary Profile for {selected_program} (SOC Code: {soc_code})",
            onet_url,
            help="Opens the official O*NET page in a new browser tab."
        )

        st.markdown("---")

        real_outcomes = st.session_state.programs.get(selected_program, [])
        numbered_outcomes = [
            f"{i+1}. {outcome}" for i, outcome in enumerate(real_outcomes)
        ]

        # ----------------------------------------------------
        # COURSE SELECTION (DEPARTMENT BUNDLE ONLY)
        # ----------------------------------------------------
        st.subheader("📚 Select Courses & Activities for Your Grid")
        dept_bundle = get_department_course_bundle(selected_program)

        selected_bundle_courses = st.multiselect(
            f"Department Course Bundle ({selected_program}):",
            options=dept_bundle,
            default=dept_bundle[:3],
        )

        custom_course = st.text_input(
            "Add a new course, experiential activity, or co-curricular experience:"
        )

        active_courses = list(selected_bundle_courses)
        if custom_course and custom_course.strip():
            active_courses.append(custom_course.strip())

        active_courses = list(dict.fromkeys(active_courses))
        st.markdown("---")

        # ----------------------------------------------------
        # INTERACTIVE GRID (CHECKBOX + CONDITIONAL LEVEL SELECTOR)
        # ----------------------------------------------------
        st.subheader(f"📊 Mapping Grid for {selected_program}")
        st.caption(
            "📌 **Tip:** Check the box under a course to map an outcome, then select the level "
            "(Introductory, Intermediate, or Advanced)."
        )

        extra_key = f"extra_outcomes_{selected_program}"
        if extra_key not in st.session_state:
            st.session_state[extra_key] = []

        with st.expander("➕ Add an extra outcome row"):
            new_outcome_text = st.text_input(
                "New outcome text:", key=f"new_outcome_input_{selected_program}"
            )
            if st.button("Add Outcome", key=f"add_outcome_btn_{selected_program}"):
                if new_outcome_text and new_outcome_text.strip():
                    st.session_state[extra_key].append(new_outcome_text.strip())
                    st.rerun()

        all_outcomes_for_grid = numbered_outcomes + [
            f"{len(numbered_outcomes) + i + 1}. {txt}"
            for i, txt in enumerate(st.session_state[extra_key])
        ]

        # Header row
        header_cols = st.columns([3] + [1] * len(active_courses))
        header_cols[0].markdown("**Program Learning Outcomes**")
        for c, course in enumerate(active_courses, start=1):
            header_cols[c].markdown(f"**{course}**")

        st.divider()

        # Outcome Rows with Checkboxes & Conditional Dropdowns
        level_values = {"Program Learning Outcomes": []}
        for course in active_courses:
            level_values[course] = []

        LEVEL_OPTIONS = ["Introductory", "Intermediate", "Advanced"]

        for row_idx, outcome_text in enumerate(all_outcomes_for_grid):
            row_cols = st.columns([3] + [1] * len(active_courses))
            row_cols[0].write(outcome_text)
            level_values["Program Learning Outcomes"].append(outcome_text)

            for c, course in enumerate(active_courses, start=1):
                check_key = f"chk_{selected_program}_{row_idx}_{course}"
                select_key = f"sel_{selected_program}_{row_idx}_{course}"

                # Render checkbox
                is_checked = row_cols[c].checkbox(
                    "Map",
                    key=check_key,
                    label_visibility="visible"
                )

                # Show level dropdown only if checked
                if is_checked:
                    assigned_level = row_cols[c].selectbox(
                        "Level",
                        options=LEVEL_OPTIONS,
                        index=0,
                        key=select_key,
                        label_visibility="collapsed"
                    )
                    level_values[course].append(assigned_level)
                else:
                    level_values[course].append("N/A")

            st.divider()

        edited_df = pd.DataFrame(level_values)

        st.markdown("---")

        # ----------------------------------------------------
        # REVIEW OUTCOMES, DOWNLOAD & FULL TEXT EDIT HISTORY
        # ----------------------------------------------------
        st.subheader("📖 Review Outcomes & Change History")

        current_outcomes_df = edited_df[
            ["Program Learning Outcomes"]
        ].dropna()

        # Download CSV
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
                                mapped_rows = group[
                                    group["is_mapped"] == True
                                ]

                                st.markdown(f"🕒 **Saved On:** `{timestamp}`")
                                st.markdown(
                                    f"📝 **Full Text Version:**\n> {past_text}"
                                )

                                if not mapped_rows.empty:
                                    level_lines = [
                                        f"{row['course']} ({row['mapping_level']})"
                                        for _, row in mapped_rows.iterrows()
                                    ]
                                    st.markdown(
                                        f"🔗 **Mapped Courses:** {', '.join(level_lines)}"
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
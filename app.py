import streamlit as st
import json
import os
import time
import re
import random
import copy

def clean_explanation(text):
    return re.sub(r'\[cite:\s*[\d,\s]+\]', '', text).strip()

def make_shuffled_pool(pool):
    """Return a deep-copied, fully randomised version of a question pool.
    Question order and each question's option order are both shuffled."""
    shuffled = copy.deepcopy(pool)
    random.shuffle(shuffled)
    for q in shuffled:
        random.shuffle(q['options'])
    return shuffled

def build_blueprint_pool(n, source):
    """Sample exactly n questions from source using BLUEPRINT_WEIGHTS.
    Uses largest-remainder rounding to guarantee the total equals n exactly."""
    by_cat = {}
    for q in source:
        cat = q.get('category', 'General')
        by_cat.setdefault(cat, []).append(copy.deepcopy(q))

    # Compute raw (float) counts, then floor them
    raw = {cat: w * n for cat, w in BLUEPRINT_WEIGHTS.items()}
    floored = {cat: int(v) for cat, v in raw.items()}
    remainder = n - sum(floored.values())

    # Distribute remainder seats to categories with largest fractional parts
    fractions = sorted(raw.items(), key=lambda x: x[1] - int(x[1]), reverse=True)
    for i in range(remainder):
        floored[fractions[i][0]] += 1

    pool = []
    for cat, count in floored.items():
        bucket = by_cat.get(cat, [])
        random.shuffle(bucket)
        pool.extend(bucket[:count])

    # Fallback: if any category was short, fill from unused questions
    if len(pool) < n:
        used_ids = {q['id'] for q in pool}
        extras = [copy.deepcopy(q) for q in source if q.get('id') not in used_ids]
        random.shuffle(extras)
        pool.extend(extras[:n - len(pool)])

    random.shuffle(pool)
    for q in pool:
        random.shuffle(q['options'])
    return pool[:n]

CATEGORY_INFO = {
    "Fundamentals of Generative AI": "Core concepts, terminology, and the ML lifecycle.",
    "Google Cloud's Generative AI Offerings": "Google's product ecosystem: Gemini, Vertex AI, NotebookLM, and more.",
    "Techniques to Improve Gen AI Model Output": "Prompting strategies, sampling parameters, and output optimisation.",
    "Business Strategies / Responsible AI & Privacy": "Strategic frameworks, human oversight, ethics, and enterprise governance.",
}

# Blueprint sampling weights (must sum to 1.0)
BLUEPRINT_WEIGHTS = {
    "Fundamentals of Generative AI": 0.30,
    "Google Cloud's Generative AI Offerings": 0.35,
    "Techniques to Improve Gen AI Model Output": 0.20,
    "Business Strategies / Responsible AI & Privacy": 0.15,
}

EXAM_SIZE_OPTIONS = {
    "Short Quick Quiz (10 Questions)": 10,
    "Medium Prep Exam (25 Questions)": 25,
    "Full Certification Simulator (45 Questions)": 45,
}

def reset_state(restart=False):
    st.session_state.started = restart
    st.session_state.current_index = 0
    st.session_state.score = 0
    st.session_state.answered = False
    st.session_state.selected_option = None
    st.session_state.results_by_category = {}
    st.session_state.active_questions = None
    st.session_state.quiz_questions = []
    st.session_state.user_answers = {}
    st.session_state.failed_question_ids = []
    if not restart:
        st.session_state.exam_size = 45

st.set_page_config(
    page_title="Gen AI Exam Simulator",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    /* Hide Streamlit header */
    header[data-testid="stHeader"] {
        display: none !important;
    }

    /* App background and font */
    .stApp { background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }

    /* Centre & limit width for easy reading */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1080px !important;
    }

    /* Splash screen animation */
    .splash-container { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background-color: #F1F5F9; display: flex; justify-content: center; align-items: center; z-index: 9999; text-align: center; animation: fadeOutToBackground 3.5s ease-in-out forwards; }
    .splash-text { font-size: 3.5rem; font-weight: 800; color: #64748B; letter-spacing: -1px; opacity: 0; animation: fadeInThenScale 1.2s ease-out 0.4s forwards; }
    @keyframes fadeInThenScale { 0% { opacity: 0; transform: scale(0.95); } 100% { opacity: 1; transform: scale(1); } }
    @keyframes fadeOutToBackground { 0% { opacity: 1; } 80% { opacity: 1; } 100% { opacity: 0; visibility: hidden; } }
    @keyframes contentFadeIn { 0% { opacity: 0; transform: translateY(10px); } 100% { opacity: 1; transform: translateY(0); } }

    /* Landing page */
    .landing-wrapper { max-width: 800px; margin: 20px auto; padding: 20px 28px; text-align: center; background-color: transparent; border-radius: 24px; border: none; box-shadow: none; opacity: 0; animation: contentFadeIn 1s cubic-bezier(0.16, 1, 0.3, 1) 3.2s forwards; }
    .section-title { font-size: 2.2rem; font-weight: 800; color: #334155; letter-spacing: -1px; margin-top: 0; margin-bottom: 8px; text-align: center; }
    .section-subtitle { font-size: 1rem; color: #64748B; margin-bottom: 20px; max-width: 640px; margin-left: auto; margin-right: auto; text-align: center; line-height: 1.6; }

    /* Premium Clickable Card Buttons */
    div.stButton > button {
        background-color: #F8FAFC !important;
        color: #334155 !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 16px !important;
        padding: 20px 40px !important;
        width: 100% !important;
        min-height: auto !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.03) !important;
        transition: all 0.25s ease !important;
        display: block !important;
        white-space: normal !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        line-height: 1.5 !important;
    }
    div.stButton > button::first-line {
        color: #0F172A !important;
        font-weight: 900 !important;
        letter-spacing: -0.3px !important;
        text-shadow: 0 1px 4px rgba(0, 0, 0, 0.12) !important;
    }
    div.stButton > button:hover {
        border-color: #0091FF !important;
        box-shadow: 0 20px 25px -5px rgba(0, 145, 255, 0.08) !important;
        transform: translateY(-4px) !important;
        background-color: #FFFFFF !important;
    }
    div.stButton > button p { text-align: left !important; margin: 4px 0 !important; }
    div.stButton > button p strong { font-size: 1.5rem !important; color: #0F172A !important; display: block !important; text-align: center !important; margin-bottom: 14px !important; }

    /* Primary action buttons */
    div[data-testid="stButton"] button {
        white-space: nowrap !important;
        min-width: fit-content !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    /* Clean spacing between rows */
    div[data-testid="stVerticalBlockGap"] {
        gap: 1rem !important;
    }

    /* Column gap for workspace layout */
    div[data-testid="stHorizontalBlock"] {
        gap: 0.75rem !important;
        margin-bottom: 0.75rem !important;
    }

    /* Main question card */
    .case-box { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 16px 20px; margin-bottom: 0px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.02); font-size: 1.2rem; line-height: 1.6; color: #1E293B; text-align: center; }
    div.stMarkdown div[style*="background-color"] {
        padding: 24px 28px !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important;
        width: 100% !important;
        max-width: 100% !important;
    }

    /* Radio button options */
    div[data-testid="stRadio"] > label { display: none !important; }
    div[data-testid="stRadio"] fieldset { text-align: center; border: none; }
    div[data-testid="stRadio"] label {
        padding: 8px 12px !important;
        font-size: 1rem !important;
        color: #1E293B !important;
    }
    div[data-testid="stRadio"] label p {
        font-size: 1rem !important;
        color: #1E293B !important;
    }
    /* Force contrast on the radio circle and its sibling text in all OS colour schemes */
    div[data-testid="stRadio"] label span {
        color: #1E293B !important;
    }

    /* Clean full-width feedback styling */
    div[data-testid="stNotification"] {
        border-radius: 10px !important;
        padding: 16px 20px !important;
    }

    .question-card { padding: 20px !important; margin-bottom: 10px !important; }

    /* ── Mobile & tablet responsive overrides ── */

    /* Tablet (≤768px) */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1.25rem !important;
            padding-bottom: 1.5rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        .splash-text { font-size: 2.2rem !important; }
        .section-title { font-size: 1.6rem !important; }
        .landing-wrapper { padding: 16px 16px !important; }
        div.stButton > button {
            padding: 14px 20px !important;
            font-size: 0.95rem !important;
        }
        div.stButton > button p strong { font-size: 1.15rem !important; }
        .case-box { font-size: 1.05rem !important; padding: 14px 16px !important; }
        div.stMarkdown div[style*="background-color"] {
            padding: 16px 18px !important;
        }
        /* Stack the top-row progress + Return Home button vertically */
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
    }

    /* Large phone (≤480px) */
    @media (max-width: 480px) {
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        .splash-text { font-size: 1.8rem !important; letter-spacing: 0 !important; }
        .section-title { font-size: 1.35rem !important; }
        .section-subtitle { font-size: 0.9rem !important; }
        div.stButton > button {
            padding: 12px 14px !important;
            font-size: 0.9rem !important;
            border-radius: 12px !important;
        }
        div.stButton > button p strong { font-size: 1rem !important; margin-bottom: 8px !important; }
        .case-box {
            font-size: 0.95rem !important;
            padding: 12px 14px !important;
            border-radius: 12px !important;
        }
        div.stMarkdown div[style*="background-color"] {
            padding: 14px 14px !important;
        }
        div[data-testid="stRadio"] label {
            padding: 6px 8px !important;
            font-size: 0.9rem !important;
            color: #1E293B !important;
        }
        div[data-testid="stRadio"] label p { font-size: 0.9rem !important; color: #1E293B !important; }
        div[data-testid="stRadio"] label span { color: #1E293B !important; }
        div[data-testid="stNotification"] { padding: 12px 14px !important; }
    }

    /* Small phone (≤320px) */
    @media (max-width: 320px) {
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        .splash-text { font-size: 1.4rem !important; }
        .section-title { font-size: 1.1rem !important; }
        div.stButton > button {
            padding: 10px 10px !important;
            font-size: 0.85rem !important;
        }
        .case-box { font-size: 0.88rem !important; padding: 10px 10px !important; }
        div[data-testid="stRadio"] label { font-size: 0.85rem !important; color: #1E293B !important; }
        div[data-testid="stRadio"] label p { font-size: 0.85rem !important; color: #1E293B !important; }
        div[data-testid="stRadio"] label span { color: #1E293B !important; }
        /* Prevent nowrap from causing overflow on tiny screens */
        div[data-testid="stButton"] button {
            white-space: normal !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

def load_questions():
    if os.path.exists('questions.json'):
        with open('questions.json', 'r', encoding='utf-8') as f: return json.load(f)
    return []

questions = load_questions()

if 'intro_done' not in st.session_state: st.session_state.intro_done = False
if 'started' not in st.session_state: st.session_state.started = False
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
    st.session_state.score = 0
    st.session_state.answered = False
    st.session_state.selected_option = None
if 'results_by_category' not in st.session_state:
    st.session_state.results_by_category = {}
if 'active_questions' not in st.session_state:
    st.session_state.active_questions = None
if 'quiz_questions' not in st.session_state:
    st.session_state.quiz_questions = []
if 'user_answers' not in st.session_state:
    st.session_state.user_answers = {}
if 'failed_question_ids' not in st.session_state:
    st.session_state.failed_question_ids = []
if 'exam_size' not in st.session_state:
    st.session_state.exam_size = 45

if not st.session_state.intro_done:
    splash_placeholder = st.empty()
    with splash_placeholder:
        st.markdown("<div class='splash-container'><div class='splash-text'>Gen AI Exam Simulator</div></div>", unsafe_allow_html=True)
    time.sleep(3.5)
    st.session_state.intro_done = True
    splash_placeholder.empty()
    st.rerun()

# SCREEN STATE 1: LAUNCH PORTAL
if not st.session_state.started and st.session_state.intro_done:
    st.markdown("<div class='landing-wrapper'>", unsafe_allow_html=True)
    st.markdown("<h1 class='section-title'>Gen AI Exam Simulator</h1>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: center; color: #64748B; font-size: 1.15rem; line-height: 1.6; margin-bottom: 40px; max-width: 750px; margin-left: auto; margin-right: auto;'>I passed the Google Cloud Gen AI exam. I built this simulator so you can check your baseline knowledge and prep for the certification without the fluff.</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    def _launch(size):
        st.session_state.exam_size = size
        st.session_state.started = True
        pool = build_blueprint_pool(size, questions)
        st.session_state.active_questions = pool
        st.session_state.quiz_questions = pool
        st.session_state.user_answers = {}
        st.session_state.current_index = 0

    with btn_col1:
        if st.button("⏱️ Short Quiz\n\n10 Questions", use_container_width=True, key="btn_short"):
            _launch(10)
            st.rerun()
    with btn_col2:
        if st.button("📊 Medium Prep\n\n25 Questions", use_container_width=True, key="btn_med"):
            _launch(25)
            st.rerun()
    with btn_col3:
        if st.button("🏆 Full Simulator\n\n45 Questions", use_container_width=True, key="btn_full"):
            _launch(45)
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# SCREEN STATE 2: CORE LIVE WORKSPACE
elif st.session_state.started:
    if not questions:
        st.error("No dataset detected inside questions.json.")
    else:
        active_qs = st.session_state.active_questions if st.session_state.active_questions is not None else questions
        if st.session_state.current_index >= len(active_qs):
            st.markdown("<br>", unsafe_allow_html=True)
            score = st.session_state.score
            total = len(active_qs)
            score_pct = int(score / total * 100) if total > 0 else 0
            theme_color = "#2ecc71" if score_pct >= 70 else "#f39c12"

            st.markdown("<h3 style='text-align: center;'>Here is your score breakdown</h3>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div style="
                    background-color: #f8f9fa;
                    padding: 24px;
                    border-radius: 12px;
                    border-left: 8px solid {theme_color};
                    margin-bottom: 28px;
                    text-align: center;
                ">
                    <span style="font-size: 16px; color: #5f6368; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">Overall Result</span>
                    <h1 style="font-size: 54px; margin: 8px 0 4px 0; color: #202124;">{score_pct}%</h1>
                    <p style="font-size: 18px; color: #3c4043; margin: 0; font-weight: 500;">You scored {score} out of {total} questions correctly</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.write("")

            for cat, data in [(c, st.session_state.results_by_category.get(c, {'correct': 0, 'total': 0})) for c in CATEGORY_INFO]:
                if data['total'] > 0:
                    pct = data['correct'] / data['total']
                    pct_display = int(pct * 100)
                    indicator = "🟢" if pct >= 0.80 else ("🟡" if pct >= 0.50 else "🔴")
                    st.markdown(f"**{indicator} {cat}** — {data['correct']} / {data['total']} correct ({pct_display}%)")
                    st.progress(pct)
                else:
                    st.markdown(f"**⚪ {cat}** — Not assessed in this session")
                st.write("")

            if st.button("New Practice Exam", use_container_width=True):
                reset_state(restart=False)
                st.rerun()

            st.write("")
            st.session_state.failed_question_ids = [
                q['id'] for q in st.session_state.quiz_questions
                if st.session_state.user_answers.get(q['id']) != q['correct']
            ]
            failed_ids = st.session_state.failed_question_ids
            if failed_ids:
                if st.button(f"Review Incorrect Questions ({len(failed_ids)})", use_container_width=True):
                    failed_pool = [q for q in questions if q.get('id') in failed_ids]
                    reset_state(restart=True)
                    pool = make_shuffled_pool(failed_pool)
                    st.session_state.active_questions = pool
                    st.session_state.quiz_questions = pool
                    st.rerun()
            else:
                st.success("Perfect score — no incorrect questions to review!")
        else:
            q = active_qs[st.session_state.current_index]
            top_col1, top_col2 = st.columns([4, 1])
            with top_col1:
                st.markdown(f"<p style='margin-top: 16px; margin-bottom: 4px;'><strong>Question {st.session_state.current_index + 1} of {len(active_qs)}</strong></p>", unsafe_allow_html=True)
            if top_col2.button("🏠 Return Home", use_container_width=True, key="reset_top"):
                reset_state(restart=False)
                st.rerun()

            categories_in_pool = set(q.get('category') for q in active_qs)
            if len(categories_in_pool) == 1:
                focus_topic = active_qs[0].get('category', 'this topic')
                st.markdown(f"**{len(active_qs)} questions on {focus_topic}**")
                st.write("")
            st.progress(st.session_state.current_index / len(active_qs))
            st.write("")
            st.markdown(f"<div class='case-box'>{q['question']}</div>", unsafe_allow_html=True)
            st.write("")
            user_choice = st.radio("Select the optimal approach:", q['options'], index=None, disabled=st.session_state.answered)

            if not st.session_state.answered:
                if st.button("Commit Choice", use_container_width=True):
                    if user_choice is not None:
                        st.session_state.selected_option = user_choice
                        st.session_state.answered = True
                        cat = q.get('category', 'General')
                        if cat not in st.session_state.results_by_category:
                            st.session_state.results_by_category[cat] = {'correct': 0, 'total': 0}
                        st.session_state.results_by_category[cat]['total'] += 1
                        if user_choice == q['correct']:
                            st.session_state.score += 1
                            st.session_state.results_by_category[cat]['correct'] += 1
                        st.session_state.user_answers[q.get('id')] = user_choice
                        st.rerun()
                    else:
                        st.warning("Please select an option before committing.")
            else:
                explanation = clean_explanation(q['explanation'])
                is_correct = st.session_state.selected_option == q['correct']
                next_label = "Complete Exam Simulation" if st.session_state.current_index == len(active_qs) - 1 else "Next Question ➡️"

                if is_correct:
                    st.success(f"**Spot on!**\n\n{explanation}")
                else:
                    st.error(f"**Not quite! Let's break it down.**\n\n**Correct answer:** {q['correct']}\n\n{explanation}")

                if st.button(next_label, key="next_question_btn", use_container_width=True):
                    st.session_state.current_index += 1
                    st.session_state.answered = False
                    st.session_state.selected_option = None
                    st.rerun()
import os
import io
import json
import re
from urllib.parse import urlparse
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from PyPDF2 import PdfReader
from PIL import Image
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
import pymysql
import pymysql.cursors

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "doc-genius-secret-key-2025")

# Vector store cache in-memory by user UID
_vector_store_cache = {}
_local_session_contexts = {}

DEFAULT_SESSION_CONTEXT = {
    "study_mode": "normal",
    "vibe_type": "default",
    "bloom_level": "Understand",
    "course_outcomes": "",
    "weightage": "5",
    "language": "English",
}

PREUPLOADED_BOOKS = [
    {
        "id": "python-book",
        "title": "Python Programming",
        "author": "S. Venkata Lakshmi",
        "subject": "Python Programming",
        "filename": "basics_of_python_programming.pdf",
    },
    {
        "id": "art-of-data-science",
        "title": "The Art of Data Science",
        "author": "Elizabeth Matsui",
        "subject": "Data Science",
        "filename": "the_art_of_data_science.pdf",
    },
    {
        "id": "project-management",
        "title": "Project Management Skills",
        "author": "Doc Genius",
        "subject": "Project Management",
        "filename": "project_management_skills.pdf",
    },
    {
        "id": "numerical-methods-in-finance",
        "title": "Numerical Methods in Finance",
        "author": "Doc Genius",
        "subject": "Finance",
        "filename": "numerical_methods_in_finance.pdf",
    },
    {
        "id": "cloud-computing",
        "title": "Intro to Cloud Computing",
        "author": "Srinath Beldona",
        "subject": "Cloud Computing",
        "filename": "introduction_to_cloud_computing.pdf",
    },
    {
        "id": "banking",
        "title": "Fundamentals of Banking",
        "author": "Doc Genius",
        "subject": "Banking",
        "filename": "fundamentals_of_banking.pdf",
    },
    {
        "id": "machine-learning",
        "title": "Programming in Standard ML",
        "author": "Robert Harper",
        "subject": "Machine Learning",
        "filename": "programming_in_standard_ML.pdf",
    },
    {
        "id": "artificial-intelligence",
        "title": "Introduction to Artificial Intelligence",
        "author": "Marc Toussaint",
        "subject": "Artificial Intelligence",
        "filename": "introduction_to_artificial_intelligence.pdf",
    },
]

BOOKS_DIR = os.path.join(app.root_path, "static", "books")


# ============================================================
# MySQL Database Connection & Initialization
# ============================================================

def _ensure_database_exists():
    db_url = os.getenv("DATABASE_URL", "")
    try:
        if db_url.startswith("mysql://") or db_url.startswith("mysql+pymysql://"):
            parsed = urlparse(db_url)
            db_name = parsed.path.lstrip("/")
            if db_name:
                conn = pymysql.connect(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or 3306,
                    user=parsed.username or "root",
                    password=parsed.password or "",
                    charset="utf8mb4"
                )
                with conn.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4")
                conn.commit()
                conn.close()
        else:
            db_name = os.getenv("MYSQL_DATABASE", os.getenv("MYSQL_DB", "blitzlearn"))
            conn = pymysql.connect(
                host=os.getenv("MYSQL_HOST", "localhost"),
                port=int(os.getenv("MYSQL_PORT", 3306)),
                user=os.getenv("MYSQL_USER", "root"),
                password=os.getenv("MYSQL_PASSWORD", ""),
                charset="utf8mb4"
            )
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4")
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Notice: MySQL database auto-creation check: {e}")


def get_db():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("mysql://") or db_url.startswith("mysql+pymysql://") or db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
        parsed = urlparse(db_url)
        port = parsed.port if (parsed.port and parsed.port != 5432) else 3306
        return pymysql.connect(
            host=parsed.hostname or "localhost",
            port=port,
            user=parsed.username or "root",
            password=parsed.password or "",
            database=parsed.path.lstrip("/") or "blitzlearn",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            charset="utf8mb4"
        )
    else:
        return pymysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", os.getenv("MYSQL_DB", "blitzlearn")),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            charset="utf8mb4"
        )


def _fetchone(cur):
    return cur.fetchone()


def _fetchall(cur):
    return cur.fetchall()


def init_db():
    _ensure_database_exists()
    ddl_statements = [
        """CREATE TABLE IF NOT EXISTS users (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            uid        VARCHAR(255) UNIQUE NOT NULL,
            name       VARCHAR(255) NOT NULL,
            email      VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

        """CREATE TABLE IF NOT EXISTS user_staged_files (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            user_uid   VARCHAR(255) NOT NULL,
            filename   VARCHAR(500) NOT NULL,
            source     VARCHAR(50)  DEFAULT 'upload',
            title      VARCHAR(500) NOT NULL,
            file_blob  LONGBLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_usf_user (user_uid)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

        """CREATE TABLE IF NOT EXISTS user_vector_chunks (
            user_uid    VARCHAR(255) PRIMARY KEY,
            chunks_clob LONGTEXT NOT NULL,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

        """CREATE TABLE IF NOT EXISTS questions (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            topic          VARCHAR(500),
            difficulty     VARCHAR(100)  NOT NULL,
            question_text  TEXT          NOT NULL,
            question_type  VARCHAR(20)   DEFAULT 'mcq',
            option_a       TEXT,
            option_b       TEXT,
            option_c       TEXT,
            option_d       TEXT,
            correct_option VARCHAR(10),
            correct_answer TEXT,
            explanation    TEXT,
            source_title   VARCHAR(1000),
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

        """CREATE TABLE IF NOT EXISTS tests (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            difficulty    VARCHAR(100)  NOT NULL,
            num_questions INTEGER       NOT NULL,
            source_title  VARCHAR(1000),
            test_format   VARCHAR(20)   DEFAULT 'mcq',
            user_id       INTEGER,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

        """CREATE TABLE IF NOT EXISTS test_questions (
            test_id        INTEGER NOT NULL,
            question_id    INTEGER NOT NULL,
            question_order INTEGER,
            PRIMARY KEY (test_id, question_id),
            CONSTRAINT fk_tq_test     FOREIGN KEY (test_id)     REFERENCES tests (id) ON DELETE CASCADE,
            CONSTRAINT fk_tq_question FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

        """CREATE TABLE IF NOT EXISTS test_attempts (
            id       INT AUTO_INCREMENT PRIMARY KEY,
            test_id  INTEGER NOT NULL,
            score    INTEGER NOT NULL,
            total    INTEGER NOT NULL,
            user_id  INTEGER,
            taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_ta_test FOREIGN KEY (test_id) REFERENCES tests (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

        """CREATE TABLE IF NOT EXISTS user_answers (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            test_id         INTEGER NOT NULL,
            question_id     INTEGER NOT NULL,
            selected_option VARCHAR(10),
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_ua_test FOREIGN KEY (test_id) REFERENCES tests (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
    ]

    try:
        conn = get_db()
        cur = conn.cursor()
        for ddl in ddl_statements:
            cur.execute(ddl)
        conn.commit()
        conn.close()
        print("Doc Genius: MySQL database initialized successfully.")
    except Exception as e:
        print(f"Notice: Database initialization deferred (MySQL not reachable or credentials not yet provided): {e}")


# Initialize database safely on startup
init_db()


# ============================================================
# Session & User Helpers
# ============================================================

def get_current_uid():
    if "uid" not in session:
        session["uid"] = "guest_user"
    return session["uid"]


def require_uid(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        uid = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ", 1)[1].strip()
            if token and token != "guest_token":
                uid = token
        if not uid:
            uid = session.get("uid", "guest_user")
        request.uid = uid
        return f(*args, **kwargs)
    return decorated_function


def _get_user_row(uid):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, uid, name, email FROM users WHERE uid = %s", (uid,))
        user = _fetchone(cur)
        if not user:
            cur.execute(
                "INSERT INTO users (uid, name, email) VALUES (%s, %s, %s)",
                (uid, "Doc Genius User", f"{uid}@docgenius.local")
            )
            conn.commit()
            user_id = cur.lastrowid
            user = {"id": user_id, "uid": uid, "name": "Doc Genius User", "email": f"{uid}@docgenius.local"}
        conn.close()
        return user
    except Exception as e:
        print(f"Notice: user lookup failed: {e}")
        return {"id": 1, "uid": uid, "name": "Doc Genius User", "email": f"{uid}@docgenius.local"}


def get_session_context(uid):
    ctx = dict(DEFAULT_SESSION_CONTEXT)
    ctx.update(_local_session_contexts.get(uid, {}))
    return ctx


def update_session_context(uid, updates):
    ctx = get_session_context(uid)
    ctx.update(updates)
    _local_session_contexts[uid] = ctx
    return ctx


# ============================================================
# Staged PDF Document & Vector Storage
# ============================================================

def get_staged_files_meta(uid):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, filename, source, title FROM user_staged_files WHERE user_uid = %s ORDER BY created_at",
            (uid,)
        )
        rows = _fetchall(cur)
        conn.close()
        return rows
    except Exception as e:
        print(f"Notice: could not load staged files from DB: {e}")
        return []


def add_staged_file_meta(uid, filename, source, title, data_bytes):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO user_staged_files (user_uid, filename, source, title, file_blob)
               VALUES (%s, %s, %s, %s, %s)""",
            (uid, filename, source, title, data_bytes)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Notice: could not save staged file blob to DB: {e}")


def clear_staged_files_meta(uid):
    if uid in _vector_store_cache:
        del _vector_store_cache[uid]
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM user_staged_files WHERE user_uid = %s", (uid,))
        cur.execute("DELETE FROM user_vector_chunks WHERE user_uid = %s", (uid,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Notice: could not clear staged files: {e}")


def remove_staged_file_meta(uid, filename):
    if uid in _vector_store_cache:
        del _vector_store_cache[uid]
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM user_staged_files WHERE user_uid = %s AND filename = %s",
            (uid, filename)
        )
        removed = cur.rowcount
        conn.commit()
        conn.close()
        return removed
    except Exception as e:
        print(f"Notice: could not remove file: {e}")
        return 0


def get_staged_file_blobs(uid):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT filename, file_blob FROM user_staged_files WHERE user_uid = %s ORDER BY created_at",
            (uid,)
        )
        rows = _fetchall(cur)
        conn.close()
        return [(r["filename"], bytes(r["file_blob"])) for r in rows if r.get("file_blob")]
    except Exception as e:
        print(f"Notice: could not fetch staged blobs: {e}")
        return []


def get_text_chunks(text):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=120)
    return text_splitter.split_text(text)


def _get_gemini_api_key():
    return (
        os.getenv("GEMINI_API_KEY") or
        os.getenv("GOOGLE_API_KEY") or
        os.getenv("GEMINI_API") or
        ""
    ).strip()


def _get_gemini_model():
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()


def _get_vision_model_candidates():
    candidates = []
    user_model = _get_gemini_model()
    if user_model:
        candidates.append(user_model)
    for fallback in ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-pro"]:
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates


def _analyze_pdf_image(pil_img, page_num, img_num, filename):
    api_key = _get_gemini_api_key()
    if not api_key:
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        if pil_img.mode not in ("RGB", "L"):
            pil_img = pil_img.convert("RGB")

        max_dim = 1600
        if max(pil_img.size) > max_dim:
            scale = max_dim / max(pil_img.size)
            new_size = (int(pil_img.size[0] * scale), int(pil_img.size[1] * scale))
            pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)

        prompt = (
            f"You are the visual document analyzer for Doc Genius.\n"
            f"This is an image/diagram found on Page {page_num} of the document '{filename}'.\n"
            f"Provide a thorough, factual analysis of this image:\n"
            f"1. Visual Type: Identify if it is a flowchart, architecture diagram, chart/graph, table, scientific figure, formula, photo, or UI screenshot.\n"
            f"2. Transcribed Text & Data: Transcribe all visible labels, titles, axis names, legends, numerical values, and formulas.\n"
            f"3. Workflow & Connections: Explain the arrows, components, hierarchies, processes, or relationships depicted.\n"
            f"4. Core Takeaway: Summarize the essential academic or technical insight this visual conveys.\n"
            f"Provide sufficient detail so that any student or user questions about this figure can be answered completely and accurately."
        )

        for candidate in _get_vision_model_candidates():
            try:
                model = genai.GenerativeModel(candidate)
                res = model.generate_content([prompt, pil_img])
                if res and res.text:
                    return res.text.strip()
            except Exception as e:
                print(f"Notice: Vision analysis failed on model '{candidate}': {e}")
                continue
    except Exception as e:
        print(f"Notice: Error analyzing image on page {page_num}: {e}")

    return None


def _get_embedding_model():
    hf_token = os.getenv("HUGGINGFACE_API_TOKEN")
    gemini_key = _get_gemini_api_key()

    if hf_token and hf_token.strip():
        return HuggingFaceEndpointEmbeddings(
            huggingfacehub_api_token=hf_token.strip(),
            repo_id="sentence-transformers/all-MiniLM-L6-v2"
        )
    elif gemini_key:
        return GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=gemini_key
        )
    else:
        raise ValueError("Missing API credentials. Please set GEMINI_API_KEY or GOOGLE_API_KEY in your .env file.")


def get_vector_store(text_chunks):
    embedding_model = _get_embedding_model()
    return FAISS.from_texts(text_chunks, embedding=embedding_model)


def get_user_vector_store(uid):
    if uid in _vector_store_cache:
        return _vector_store_cache[uid]

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT chunks_clob FROM user_vector_chunks WHERE user_uid = %s", (uid,))
        row = _fetchone(cur)
        conn.close()

        if not row or not row.get("chunks_clob"):
            return None

        chunks = json.loads(row["chunks_clob"])
        store = get_vector_store(chunks)
        _vector_store_cache[uid] = store
        return store
    except Exception as e:
        print(f"Notice: vector store loading: {e}")
        return None


def set_user_vector_store(uid, store, chunks):
    _vector_store_cache[uid] = store
    try:
        chunks_json = json.dumps(chunks)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO user_vector_chunks (user_uid, chunks_clob)
               VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE
                   chunks_clob = VALUES(chunks_clob),
                   updated_at  = CURRENT_TIMESTAMP""",
            (uid, chunks_json)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Notice: could not persist vector chunks to DB: {e}")


# ============================================================
# Conversational RAG & Study Modes (Normal + Vibe Modes)
# ============================================================

def get_conversational_chain(study_mode="normal", vibe_type="default", bloom_level="Understand", outcomes="", weightage="5", language="English"):
    api_key = _get_gemini_api_key()
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY or GOOGLE_API_KEY in environment variables (.env).")

    base_instruction = """
    You are Doc Genius, an intelligent academic and document analysis tutor.
    Answer questions accurately and directly based on the provided PDF context.
    The context includes both the textual content and thorough visual analyses of any figures, diagrams, flowcharts, charts, architectures, or illustrations present in the document.
    When answering questions regarding diagrams, images, or figures, provide clear, detailed explanations of their components, workflows, labels, and takeaways, citing page numbers whenever available.
    """

    if study_mode == "professor":
        mode_instruction = """
        PROFESSOR MODE:
        Provide highly structured, rigorous, and intellectually deep answers.
        Use precise domain terminology, clearly define core concepts, and provide
        academic reasoning suitable for university examinations.
        """
        active_language = "English (Formal & Technical)"
    elif study_mode == "vibe":
        if vibe_type == "mumbai":
            active_language = "Hinglish (Mumbai Slang)"
            mode_instruction = """
            MUMBAI CHA BHAI MODE:
            Talk like a cool, sharp Mumbai friend explaining concepts at a tapri with cutting chai.
            Use Mumbai slang naturally — words like 'bhai', 'bhidu', 'apun', 'ekdum jhakaas',
            'bindaas', 'mast', 'funda', 'scene', 'dimaag ki batti', etc.
            Keep it entertaining and crystal clear: "Arre bhidu, sun! Yeh concept ekdum simple hai..."
            """
        elif vibe_type == "hyderabadi":
            active_language = "Hinglish (Hyderabadi Slang)"
            mode_instruction = """
            HYDERABADI MIA MODE:
            Explain concepts in authentic, friendly Hyderabadi flavor.
            Use Hyderabadi slang naturally — words like 'mia', 'hau', 'nakko', 'baigan', 'kiraak',
            'potti', 'kaiku fikar karte', 'scene kya hai', etc.
            Make it warm and fun: "Arre mia, kaiku tension lere? Yeh topic toh ekdum kiraak hai..."
            """
        elif vibe_type == "punjabi":
            active_language = "Hinglish (Punjabi Slang)"
            mode_instruction = """
            PUNJAB DA PUTTAR MODE:
            Explain concepts with full Punjabi energy and brotherly warmth!
            Use Punjabi slang naturally — words like 'paaji', 'veer', 'chak de phatte',
            'balle balle', 'ghaint', 'vadiya', 'kamaal', 'sohneyo', etc.
            Keep it vibrant: "Oye paaji, chak de phatte! Yeh concept toh bilkul vadiya hai..."
            """
        else:
            active_language = "Hinglish (Conversational)"
            mode_instruction = """
            CASUAL HINGLISH VIBE:
            Explain concepts in a casual, relatable blend of Hindi and English.
            Talk like friends studying together before an exam. Example: "Dekho, basic concept yeh hai..."
            """
    else:
        active_language = language or "English"
        mode_instruction = """
        NORMAL MODE:
        Provide clear, well-explained, and easily digestible answers.
        Balance technical clarity with approachable explanations.
        """

    prompt_template = f"""
    {base_instruction}

    {mode_instruction}

    Learner Level: {bloom_level}
    Style/Language: {active_language}

    Rules:
    1. Answer using the provided Context whenever relevant.
    2. If the context does not contain the answer, say honestly: "I couldn't find that specific information in your uploaded document."
    3. Maintain your designated study mode persona consistently.
    4. Highlight key terms and steps using markdown formatting.

    Context:
    {{context}}

    Question:
    {{question}}

    Answer:
    """

    model_name = _get_gemini_model()
    model = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0.3
    )
    prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
    return load_qa_chain(model, chain_type="stuff", prompt=prompt)


# ============================================================
# Exam Mode / AI Quiz Generator
# ============================================================

VALID_DIFFICULTIES = ("easy", "medium", "hard")
VALID_QUESTION_COUNTS = (5, 10, 15, 20)

DIFFICULTY_GUIDES = {
    "easy": "Fundamental recall, definitions, and direct concept questions.",
    "medium": "Application, reasoning, and scenario-based questions.",
    "hard": "In-depth analytical, evaluative, and multi-concept questions."
}


def _clean_json_response(raw_text):
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def _gather_test_context(store, num_questions):
    seed_queries = [
        "key definitions and fundamental concepts",
        "mechanisms, processes, and core workflows",
        "real world applications and practical use cases",
        "differences, comparisons, and structural details"
    ]
    docs = []
    seen = set()
    for q in seed_queries:
        for doc in store.similarity_search(q, k=4):
            content_snippet = doc.page_content[:200]
            if content_snippet not in seen:
                seen.add(content_snippet)
                docs.append(doc)
    return "\n\n".join(doc.page_content for doc in docs[:12])


def _generate_questions_from_notes(uid, difficulty, num_questions):
    store = get_user_vector_store(uid)
    if store is None:
        return None, ("No processed document found. Please upload a PDF and click 'Process Content' first.", 400)

    api_key = _get_gemini_api_key()
    if not api_key:
        return None, ("GEMINI_API_KEY or GOOGLE_API_KEY is not configured in .env. Please set it to generate exams.", 500)

    context = _gather_test_context(store, num_questions)
    diff_guide = DIFFICULTY_GUIDES.get(difficulty, DIFFICULTY_GUIDES["medium"])

    prompt = f"""
    You are an expert exam question creator.
    Generate exactly {num_questions} high-quality Multiple Choice Questions (MCQs) based STRICTLY on the document context below.

    Difficulty: {difficulty.upper()} ({diff_guide})

    Instructions:
    1. Each question must test understanding of real technical ideas and concepts from the document.
    2. Do NOT create meta-questions about the document structure (no questions about page numbers, authors, publishers, or chapter titles).
    3. Provide 4 distinct, plausible options (a, b, c, d).
    4. Provide the correct option key ("a", "b", "c", or "d").
    5. Provide a 1-2 sentence explanation of why that option is correct based on the text.
    6. Provide a concise topic tag (2-4 words) for each question.

    Return ONLY a valid JSON array with NO markdown fences, commentary, or extra text. Format:
    [
      {{
        "topic": "Concept Name",
        "question": "Question text?",
        "options": {{
          "a": "Option A text",
          "b": "Option B text",
          "c": "Option C text",
          "d": "Option D text"
        }},
        "correct_option": "a",
        "explanation": "Clear explanation of the correct answer."
      }}
    ]

    Context:
    {context}
    """

    try:
        model_name = _get_gemini_model()
        model = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0.4)
        response = model.invoke(prompt)
        questions = json.loads(_clean_json_response(response.content))
    except Exception as e:
        print(f"Error generating test questions: {e}")
        return None, ("Failed to generate questions. Ensure your GEMINI_API_KEY is valid.", 500)

    if not isinstance(questions, list) or len(questions) == 0:
        return None, ("Failed to parse generated questions. Please try again.", 500)

    questions = [
        q for q in questions
        if q.get("question") and q.get("options") and q.get("correct_option")
    ][:num_questions]

    staged = get_staged_files_meta(uid)
    source_title = ", ".join(sorted({f.get("title", f["filename"]) for f in staged})) or "Uploaded PDF Notes"

    test_id = 1
    saved_questions = []

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tests (difficulty, num_questions, source_title, test_format) VALUES (%s, %s, %s, %s)",
            (difficulty, len(questions), source_title, "mcq")
        )
        test_id = cur.lastrowid

        for i, q in enumerate(questions):
            opts = q["options"]
            cur.execute(
                """INSERT INTO questions
                   (topic, difficulty, question_text, question_type, option_a, option_b, option_c, option_d,
                    correct_option, explanation, source_title)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    q.get("topic", "General"), difficulty, q["question"], "mcq",
                    opts.get("a", ""), opts.get("b", ""), opts.get("c", ""), opts.get("d", ""),
                    q["correct_option"].lower(), q.get("explanation", ""), source_title
                )
            )
            q_id = cur.lastrowid
            cur.execute(
                "INSERT INTO test_questions (test_id, question_id, question_order) VALUES (%s, %s, %s)",
                (test_id, q_id, i)
            )
            saved_questions.append({
                "id": q_id,
                "topic": q.get("topic", "General"),
                "question": q["question"],
                "options": opts,
                "correct_option": q["correct_option"].lower(),
                "explanation": q.get("explanation", "")
            })
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Notice: database save for test: {e}")
        # In-memory fallback if MySQL is offline
        for i, q in enumerate(questions):
            saved_questions.append({
                "id": i + 1,
                "topic": q.get("topic", "General"),
                "question": q["question"],
                "options": q["options"],
                "correct_option": q["correct_option"].lower(),
                "explanation": q.get("explanation", "")
            })

    return {
        "test_id": test_id,
        "difficulty": difficulty,
        "source_title": source_title,
        "questions": saved_questions
    }, None


# ============================================================
# Core Application Routes
# ============================================================

@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/chat')
def chat():
    return render_template('chat.html')


@app.route('/tests')
def tests():
    return render_template('tests.html')


@app.route('/history')
def history():
    return render_template('history.html')


@app.route('/login')
@app.route('/signup')
@app.route('/profile')
@app.route('/terms')
@app.route('/about')
def redirect_to_dashboard():
    return redirect(url_for('dashboard'))


@app.route('/static/js/firebase-config.js')
def firebase_mock_js():
    js = """
    // Doc Genius standalone guest auth
    const mockUser = {
        uid: "guest_user",
        email: "guest@docgenius.local",
        displayName: "Doc Genius User",
        photoURL: null,
        getIdToken: async function() { return "guest_token"; }
    };

    const mockAuth = {
        currentUser: mockUser,
        onAuthStateChanged: function(callback) {
            setTimeout(function() { callback(mockUser); }, 20);
        },
        signOut: async function() {
            window.location.href = '/dashboard';
        }
    };

    window.firebase = {
        apps: [{}],
        initializeApp: function() {},
        auth: function() { return mockAuth; }
    };
    window.auth = mockAuth;
    window.getAuth = function() { return mockAuth; };

    async function authFetch(url, options = {}) {
        const headers = Object.assign({}, options.headers, {
            "Authorization": "Bearer guest_token"
        });
        return fetch(url, Object.assign({}, options, { headers }));
    }
    """
    from flask import Response
    return Response(js, mimetype="application/javascript")


# ============================================================
# Document & PDF Management APIs
# ============================================================

@app.route('/api/books', methods=['GET'])
def get_books():
    return jsonify(PREUPLOADED_BOOKS)


@app.route('/upload_stage', methods=['POST'])
@require_uid
def upload_stage():
    uid = request.uid
    files = request.files.getlist("pdf_files")
    if not files or files[0].filename == '':
        return jsonify({"error": "No PDF files selected"}), 400

    added = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            continue
        data_bytes = f.read()
        add_staged_file_meta(uid, f.filename, "upload", f.filename, data_bytes)
        added.append(f.filename)

    if not added:
        return jsonify({"error": "Only PDF files are supported"}), 400

    return jsonify({"message": f"{len(added)} PDF document(s) uploaded successfully", "files": added})


@app.route('/select_book', methods=['POST'])
@require_uid
def select_book():
    uid = request.uid
    data = request.json or {}
    book_id = data.get("book_id")
    book = next((b for b in PREUPLOADED_BOOKS if b["id"] == book_id), None)
    if not book:
        return jsonify({"error": "Book not found"}), 404

    path = os.path.join(BOOKS_DIR, book["filename"])
    if not os.path.exists(path):
        return jsonify({"error": f"'{book['title']}' is not available on the server."}), 404

    with open(path, "rb") as fh:
        data_bytes = fh.read()

    add_staged_file_meta(uid, book["filename"], "book", book["title"], data_bytes)

    return jsonify({
        "message": f"'{book['title']}' loaded into your documents",
        "title": book["title"],
        "filename": book["filename"]
    })


@app.route('/staged_files', methods=['GET'])
@require_uid
def staged_files_list():
    meta = get_staged_files_meta(request.uid)
    return jsonify(meta)


@app.route('/staged_files', methods=['DELETE'])
@require_uid
def clear_staged_files():
    clear_staged_files_meta(request.uid)
    return jsonify({"message": "All documents removed"})


@app.route('/staged_files/<path:filename>', methods=['DELETE'])
@require_uid
def remove_staged_file(filename):
    removed = remove_staged_file_meta(request.uid, filename)
    if not removed:
        return jsonify({"error": "Document not found"}), 404
    return jsonify({"message": f"'{filename}' removed"})


@app.route('/process', methods=['POST'])
@require_uid
def process_content():
    uid = request.uid
    staged = get_staged_file_blobs(uid)

    if not staged:
        return jsonify({
            "error": "No PDF documents found. Please upload a PDF or select a sample book first."
        }), 400

    raw_text = ""
    total_images_indexed = 0

    for filename, data_bytes in staged:
        file_text = ""
        file_images_summary = []
        try:
            pdf_reader = PdfReader(io.BytesIO(data_bytes))
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                # 1. Text extraction
                extracted_page_text = page.extract_text()
                if extracted_page_text and extracted_page_text.strip():
                    file_text += f"\n[Page {page_num} Text]:\n" + extracted_page_text + "\n"

                # 2. Image extraction & Vision analysis
                try:
                    page_images = list(page.images)
                except Exception as img_err:
                    page_images = []

                img_count_on_page = 0
                for img_obj in page_images:
                    if total_images_indexed >= 25:
                        break  # Safeguard against excessive API calls on huge image-dense documents
                    try:
                        img_bytes = img_obj.data
                        pil_img = Image.open(io.BytesIO(img_bytes))
                        w, h = pil_img.size

                        # Filter out tiny icons, decorative dividers, bullets
                        if w < 75 or h < 75:
                            continue
                        if (w / max(h, 1) > 25) or (h / max(w, 1) > 25):
                            continue

                        img_count_on_page += 1
                        total_images_indexed += 1
                        analysis = _analyze_pdf_image(pil_img, page_num, img_count_on_page, filename)
                        if analysis:
                            fig_block = (
                                f"\n\n--- [FIGURE / DIAGRAM ON PAGE {page_num} (Figure #{img_count_on_page}) OF '{filename}'] ---\n"
                                f"{analysis}\n"
                                f"--- [END OF FIGURE ON PAGE {page_num}] ---\n\n"
                            )
                            file_text += fig_block
                            file_images_summary.append(f"Page {page_num} (Figure #{img_count_on_page})")
                    except Exception as single_img_err:
                        print(f"Notice: Could not parse image on page {page_num}: {single_img_err}")

            if file_images_summary:
                overview = (
                    f"\n\n[DOCUMENT VISUAL INDEX for '{filename}']:\n"
                    f"This document contains {len(file_images_summary)} diagram(s)/image(s) on: {', '.join(file_images_summary)}.\n"
                    f"[END OF DOCUMENT VISUAL INDEX]\n\n"
                )
                file_text = overview + file_text

            raw_text += file_text + "\n"
        except Exception as e:
            print(f"Error reading PDF '{filename}': {e}")

    if not raw_text.strip():
        return jsonify({"error": "Could not extract text or visual content from the selected PDF(s). Please verify the document is valid."}), 400

    try:
        text_chunks = get_text_chunks(raw_text)
        store = get_vector_store(text_chunks)
        set_user_vector_store(uid, store, text_chunks)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        print(f"Error creating vector store: {e}")
        return jsonify({"error": f"Failed to build search index: {str(e)}"}), 500

    indexed_msg = f"Document processed and indexed successfully! ({len(text_chunks)} sections"
    if total_images_indexed > 0:
        indexed_msg += f", {total_images_indexed} diagram/image figures analyzed"
    indexed_msg += ")."

    return jsonify({
        "message": indexed_msg,
        "chunks_count": len(text_chunks),
        "images_count": total_images_indexed
    })


@app.route('/processed_status', methods=['GET'])
@require_uid
def processed_status():
    uid = request.uid
    store = get_user_vector_store(uid)
    staged = get_staged_files_meta(uid)
    return jsonify({
        "ready": store is not None,
        "staged_files_count": len(staged),
        "files": staged
    })


# ============================================================
# Q&A / Chat APIs (Normal & Vibe Modes)
# ============================================================

@app.route('/ask', methods=['POST'])
@require_uid
def ask():
    uid = request.uid
    data = request.json or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "Please provide a question."}), 400

    store = get_user_vector_store(uid)
    if store is None:
        return jsonify({
            "answer": "Please process a document first! Go to the Dashboard, upload or select a PDF, and click 'Process Document'."
        })

    try:
        docs = store.similarity_search(question, k=5)
        ctx = get_session_context(uid)

        chain = get_conversational_chain(
            study_mode=ctx.get("study_mode", "normal"),
            vibe_type=ctx.get("vibe_type", "default"),
            bloom_level=ctx.get("bloom_level", "Understand"),
            language=ctx.get("language", "English")
        )

        response = chain({"input_documents": docs, "question": question}, return_only_outputs=True)
        return jsonify({"answer": response["output_text"]})
    except ValueError as ve:
        return jsonify({"answer": f"API Key Notice: {str(ve)}"}), 400
    except Exception as e:
        print(f"Error answering question: {e}")
        return jsonify({"answer": f"Error generating answer: {str(e)}"}), 500


@app.route('/mode-change', methods=['POST'])
@require_uid
def mode_change():
    data = request.json or {}
    study_mode = data.get("study_mode", "normal")
    vibe_type = data.get("vibe_type", "default")

    update_session_context(request.uid, {
        "study_mode": study_mode,
        "vibe_type": vibe_type
    })

    return jsonify({
        "message": f"Mode updated to {study_mode} ({vibe_type})",
        "study_mode": study_mode,
        "vibe_type": vibe_type
    })


# ============================================================
# Exam APIs
# ============================================================

@app.route('/generate_test', methods=['POST'])
def generate_test():
    data = request.json or {}
    difficulty = data.get("difficulty", "medium")
    num_questions = data.get("num_questions", 10)
    uid = data.get("uid") or session.get("uid", "guest_user")

    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "medium"
    try:
        num_questions = int(num_questions)
    except (TypeError, ValueError):
        num_questions = 10
    if num_questions not in VALID_QUESTION_COUNTS:
        num_questions = 10

    result, error = _generate_questions_from_notes(uid, difficulty, num_questions)
    if error:
        msg, code = error
        return jsonify({"error": msg}), code

    return jsonify(result)


@app.route('/submit_test', methods=['POST'])
def submit_test():
    data = request.json or {}
    test_id = data.get("test_id")
    score = data.get("score")
    total = data.get("total")
    uid = data.get("uid") or session.get("uid", "guest_user")
    answers = data.get("answers", {})

    if test_id is None or score is None or total is None:
        return jsonify({"error": "Missing test_id, score, or total"}), 400

    try:
        user_row = _get_user_row(uid)
        user_id = user_row["id"] if user_row else None

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO test_attempts (test_id, score, total, user_id) VALUES (%s, %s, %s, %s)",
            (test_id, score, total, user_id)
        )
        attempt_id = cur.lastrowid

        for q_id, selected_opt in answers.items():
            try:
                cur.execute(
                    "INSERT INTO user_answers (test_id, question_id, selected_option) VALUES (%s, %s, %s)",
                    (test_id, int(q_id), str(selected_opt))
                )
            except Exception:
                pass

        conn.commit()
        conn.close()
        return jsonify({"message": "Test submitted successfully", "attempt_id": attempt_id})
    except Exception as e:
        print(f"Notice: saving test attempt to DB: {e}")
        return jsonify({"message": "Test score recorded locally", "score": score, "total": total})


@app.route('/api/my_tests/<uid>', methods=['GET'])
def get_user_tests(uid):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT ta.id, ta.test_id, ta.score, ta.total, ta.taken_at,
                   t.difficulty, t.source_title
            FROM test_attempts ta
            JOIN tests t ON ta.test_id = t.id
            JOIN users u ON ta.user_id = u.id
            WHERE u.uid = %s
            ORDER BY ta.taken_at DESC
        """, (uid,))
        rows = _fetchall(cur)
        conn.close()

        formatted = []
        for r in rows:
            formatted.append({
                "id": r["id"],
                "test_id": r["test_id"],
                "score": r["score"],
                "total": r["total"],
                "percentage": round((r["score"] / r["total"]) * 100, 1) if r["total"] > 0 else 0,
                "difficulty": r["difficulty"],
                "source_title": r["source_title"],
                "taken_at": r["taken_at"].strftime("%Y-%m-%d %H:%M") if hasattr(r["taken_at"], "strftime") else str(r["taken_at"])
            })
        return jsonify(formatted)
    except Exception as e:
        print(f"Notice: loading my_tests: {e}")
        return jsonify([])


@app.route('/api/test_detail/<int:test_id>', methods=['GET'])
def get_test_detail(test_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT q.id, q.topic, q.difficulty, q.question_text, q.option_a, q.option_b,
                   q.option_c, q.option_d, q.correct_option, q.explanation, tq.question_order
            FROM questions q
            JOIN test_questions tq ON q.id = tq.question_id
            WHERE tq.test_id = %s
            ORDER BY tq.question_order
        """, (test_id,))
        q_rows = _fetchall(cur)

        cur.execute("""
            SELECT question_id, selected_option
            FROM user_answers
            WHERE test_id = %s
        """, (test_id,))
        ans_rows = _fetchall(cur)
        conn.close()

        user_answers = {a["question_id"]: a["selected_option"] for a in ans_rows}

        questions = []
        for q in q_rows:
            questions.append({
                "id": q["id"],
                "topic": q["topic"],
                "difficulty": q["difficulty"],
                "question": q["question_text"],
                "options": {
                    "a": q["option_a"],
                    "b": q["option_b"],
                    "c": q["option_c"],
                    "d": q["option_d"]
                },
                "correct_option": q["correct_option"],
                "selected_option": user_answers.get(q["id"]),
                "explanation": q["explanation"]
            })
        return jsonify({"test_id": test_id, "questions": questions})
    except Exception as e:
        print(f"Notice: loading test detail: {e}")
        return jsonify({"error": "Failed to load test detail"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
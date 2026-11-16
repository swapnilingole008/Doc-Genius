# Doc Genius — Intelligent PDF Q&A & Exam Engine

Doc Genius is a streamlined, AI-powered learning and document analysis platform. Upload any PDF study material, textbook, or research document to ask questions in interactive conversational modes (including regional Indian Vibe personas) and test your knowledge through custom, auto-generated exams with instant scoring and explanations.

---

## 🌟 Key Features

### 1. Document Management & Ingestion (RAG)
- **PDF Upload**: Upload one or more PDF documents (chapters, lecture notes, textbooks).
- **Pre-Uploaded Library**: Select from standard sample books (Python Programming, Data Science, AI, Cloud Computing, Banking, etc.) without needing an immediate file upload.
- **RAG Pipeline**:
  - Text extraction with `PyPDF2`.
  - Recursive chunking with LangChain's `RecursiveCharacterTextSplitter`.
  - Dense semantic embeddings with HuggingFace (`sentence-transformers/all-MiniLM-L6-v2`) or Google Generative AI embeddings.
  - In-memory vector indexing powered by `FAISS`.

### 2. Conversational Q&A & Study Modes
- **Normal Mode**: Balanced, comprehensive academic answers strictly derived from the context of your uploaded PDF.
- **Professor Mode**: Academically rigorous, highly structured explanations using formal domain terminology, ideal for university exams.
- **Vibe Modes (Fun & Relatable Indian Personas)**:
  - 🌴 **Mumbai Cha Bhai**: "Bhidu style" casual explanations ("Arre bhidu, sun! Yeh concept ekdum simple hai...").
  - 👑 **Hyderabadi Mia**: Authentic, friendly Hyderabadi flavor ("Arre mia, kaiku tension lere? Yeh topic toh ekdum kiraak hai...").
  - 🌾 **Punjab Da Puttar**: Energetic, brotherly Punjabi tone ("Oye paaji chak de phatte!").
  - 🇮🇳 **Casual Hinglish**: Conversational mix of Hindi and English.

### 3. Exam Mode & AI Quiz Engine
- **Customizable Assessments**:
  - **Difficulty Levels**: Easy (recall & definitions), Medium (application & analysis), Hard (reasoning & scenarios).
  - **Question Count**: 5, 10, 15, or 20 questions.
- **Interactive Quiz Runner**:
  - Question counter, elapsed timer, and visual progress bar.
  - Interactive option selection (A, B, C, D).
  - Question grid navigator to jump between questions.
- **Instant Scoring & Review**:
  - Immediate percentage score and grade summary.
  - Question-by-question breakdown showing your choice, the correct answer, and **detailed AI explanations citing the uploaded document**.
  - All test attempts and scores are saved to your MySQL database.

### 4. Test History
- Review past exam attempts, scores, and percentages in a clean table format without cluttered graphs or charts.
- Inspect full question-and-answer details of any previous attempt.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.10+, Flask, Gunicorn
- **Database**: MySQL (via `pymysql`)
- **AI & LLM**: Google Gemini (`gemini-2.5-flash`) via `langchain-google-genai`
- **Embeddings**: HuggingFace Inference API (`sentence-transformers/all-MiniLM-L6-v2`) or Gemini Embeddings
- **Vector Search**: `faiss-cpu`
- **Frontend**: Vanilla HTML5, CSS3 (Modern Glassmorphic Dark/Light Mode), JavaScript (ES6)

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher
- A running MySQL server (e.g. MySQL 8.0, XAMPP, or MariaDB)

### 2. Installation
```powershell
# Clone or navigate to the project directory
cd "d:\Doc Genius"

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Copy `.env.example` to `.env` or edit `.env`:
```dotenv
# AI Credentials (Required for Q&A and Exam Generation)
GEMINI_API_KEY=your_gemini_api_key_here
HUGGINGFACE_API_TOKEN=your_huggingface_api_token_here

# MySQL Database Connection
DATABASE_URL=mysql://root:your_password@localhost:3306/blitzlearn
# Or individual parameters:
# MYSQL_HOST=localhost
# MYSQL_PORT=3306
# MYSQL_USER=root
# MYSQL_PASSWORD=your_password
# MYSQL_DATABASE=blitzlearn

FLASK_SECRET_KEY=doc-genius-secret-key-2025
```

### 4. Run the Application
```powershell
python app.py
```
Open your browser and navigate to:
**`http://localhost:5000`**

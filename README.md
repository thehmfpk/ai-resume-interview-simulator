# AI Resume-Based Interview Simulator

An AI-powered interview simulator that reads an uploaded resume, detects the
candidate's domain and skills, generates 10 personalised interview questions
with **Groq LLMs**, runs a timed mock interview, and evaluates the answers
with a second independent AI pipeline — all wrapped in a clean, responsive
Flask web app.

Built for the TEEROP (SMC-PRIVATE) LIMITED AI & Machine Learning Internship — Task 03.

---

## ✨ Features

- **Resume upload & parsing** — PDF text extraction via `pdfplumber` (with a `PyPDF2` fallback).
- **AI domain detection** — skills, technologies, projects and seniority are extracted automatically.
- **Two independent Groq pipelines**
  - **Model 1 — Question Generator**: analyzes the resume and produces exactly 10 resume-grounded questions.
  - **Model 2 — Answer Evaluator**: scores each response, explains why, and produces an overall report.
- **Two interview modes** — Multiple Choice (MCQ) or free-text Question & Answer.
- **Difficulty levels** — Easy / Medium / Hard / Adaptive.
- **Live interview UI** — progress bar, question counter, per-question countdown ring, dot-track navigation.
- **Performance dashboard** — overall score ring, correct/incorrect counts, performance rating, strengths, weaknesses, AI recommendations, full question-by-question breakdown.
- **Generate 10 more questions** — fresh, non-repeating follow-up round.
- **Downloadable PDF report** (bonus).
- **Interview history** for the current session (bonus).
- **Dark mode** toggle (bonus).
- **Light theme** — white / soft mint surfaces / deep pine green / navy blue / black, consistent across every screen.

---

## 🏗️ Architecture

```
Browser  ─▶  Flask routes (app.py)  ─▶  resume_parser.py   (PDF → text)
                                    ─▶  groq_service.py     (Groq LLM calls)
                                          ├─ analyze_resume()      \  MODEL 1
                                          ├─ generate_questions()  /  (question generator)
                                          └─ evaluate_answers()       MODEL 2 (evaluator)
```

Resume text and generated questions/answers are kept in the Flask **session**
(server-signed cookie) — nothing is written to a database, so the app has
zero external storage dependencies beyond the Groq API.

Answer keys (`correct_answer` for MCQ, `expected_answer` for Q&A) are **never
sent to the browser** — only the question text and options are rendered
client-side; grading happens entirely on the server.

---

## 📁 Project Structure

```
interview-simulator/
├── app.py                  # Flask routes / application logic
├── groq_service.py         # Groq API pipelines (question generator + evaluator)
├── resume_parser.py        # PDF text extraction
├── requirements.txt
├── .env.example             # copy to .env and add your GROQ_API_KEY
├── sample_resume/
│   └── sample_resume.pdf    # sample resume for testing
├── templates/
│   ├── base.html
│   ├── index.html            # landing / upload page
│   ├── interview.html        # live interview UI
│   ├── results.html          # performance dashboard
│   └── history.html          # session interview history
└── static/
    ├── css/style.css         # design system (light + dark theme)
    └── js/                   # main.js, interview.js, theme.js
```

---

## 🚀 Setup Instructions

**Requirements:** Python 3.13, a free [Groq API key](https://console.groq.com/keys), VS Code (or any editor).

1. **Clone / open the project folder in VS Code.**

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS / Linux
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Add your Groq API key:**
   - Copy `.env.example` to a new file named `.env`
   - Open `.env` and paste your key:
     ```
     GROQ_API_KEY=gsk_your_real_key_here
     ```

5. **Run the app:**
   ```bash
   python app.py
   ```

6. Open your browser at **http://127.0.0.1:5000**

7. Upload the included `sample_resume/sample_resume.pdf` (or your own PDF resume) to try it out.

---

## 🧪 Testing the flow

1. Upload a resume → choose MCQ or Q&A → choose a difficulty → **Analyze Resume & Start Interview**.
2. Answer the 10 questions (timer runs per question; progress bar and dot-track show where you are).
3. On the last question, click **Submit Interview** — the AI evaluator scores your answers.
4. Review your **Performance Dashboard**: score ring, strengths, weaknesses, recommendations, and a full per-question breakdown.
5. Click **Generate 10 More Questions** to get a fresh, non-repeating round, or **Download PDF Report** to save your results.

---

## ⚙️ Configuration notes

- `GROQ_MODEL` in `.env` defaults to `llama-3.3-70b-versatile`. You can swap in any chat-completion-capable Groq model.
- Max resume upload size is 8 MB, PDF only.
- Session data (resume text, questions, results, history) lives only in the signed browser cookie for the current session — restarting the Flask server does not lose an active browser session's data, but clearing cookies does.

---

## 📌 Notes on the two-model architecture (per assignment spec)

| | Model 1 — Question Generator | Model 2 — Evaluator |
|---|---|---|
| Function | `analyze_resume()`, `generate_questions()` | `evaluate_answers()` |
| Input | Raw resume text | Profile + questions + candidate answers |
| Output | Domain, skills, projects, 10 questions | Per-question score, correctness, strengths, weaknesses, recommendations, overall score |

Both call the Groq chat-completions API independently, so either pipeline's
prompt or model can be changed without touching the other — exactly the
modular architecture required by the assignment brief.

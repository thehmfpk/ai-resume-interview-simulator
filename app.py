"""
app.py
------
AI Resume-Based Interview Simulator — Flask backend.

Workflow implemented:
  1. Upload Resume (PDF)
  2. Extract Resume Text            (resume_parser.py)
  3. Detect Candidate Domain        (groq_service.analyze_resume  -> MODEL 1)
  4. Generate 10 Interview Questions(groq_service.generate_questions -> MODEL 1)
  5. Candidate Attempts Interview   (/interview)
  6. AI Evaluates Responses         (groq_service.evaluate_answers -> MODEL 2)
  7. Performance Dashboard          (/results)
  8. Generate 10 Additional Questions (/generate-more)
"""

import os
import io
import uuid
import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, send_file
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask_session import Session

import resume_parser
import groq_service

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap

# --------------------------------------------------------------------------- #
# Server-side sessions.
#
# Flask's DEFAULT session is stored entirely inside the browser cookie
# (signed, but not encrypted, and capped around 4KB by most browsers).
# This app stores a full resume profile, 10 questions, and a full evaluation
# report in the session — that comfortably exceeds the cookie limit, which
# silently drops data and makes /results say "no results" right after a
# successful submission. It also means a candidate could decode their own
# cookie and read the correct answers before finishing the interview.
#
# Storing sessions on disk (server-side) fixes both problems: the cookie
# only holds a small session ID, and the real data never reaches the browser.
# --------------------------------------------------------------------------- #
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(os.path.dirname(__file__), ".flask_session")
app.config["SESSION_PERMANENT"] = False
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
Session(app)

QUESTION_TIME_SECONDS = {"Easy": 60, "Medium": 90, "Hard": 120, "Adaptive": 90}


# --------------------------------------------------------------------------- #
# Landing / Upload
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("resume")
    mode = request.form.get("mode", "mcq")
    difficulty = request.form.get("difficulty", "Adaptive")

    if not file or file.filename == "":
        flash("Please choose a resume PDF to upload.", "error")
        return redirect(url_for("index"))

    if not resume_parser.allowed_file(file.filename):
        flash("Only PDF resumes are supported right now.", "error")
        return redirect(url_for("index"))

    try:
        file_bytes = file.read()
        resume_text = resume_parser.extract_resume_text(file_bytes)
        profile = groq_service.analyze_resume(resume_text)
        questions = groq_service.generate_questions(profile, mode, difficulty)
    except Exception as exc:
        flash(f"Something went wrong while processing your resume: {exc}", "error")
        return redirect(url_for("index"))

    session["resume_filename"] = secure_filename(file.filename)
    session["profile"] = profile
    session["mode"] = mode
    session["difficulty"] = difficulty
    session["questions"] = questions
    session["asked_questions"] = [q["question"] for q in questions]
    session["round"] = 1
    session.pop("results", None)

    return redirect(url_for("interview"))


# --------------------------------------------------------------------------- #
# Interview
# --------------------------------------------------------------------------- #
@app.route("/interview")
def interview():
    questions = session.get("questions")
    profile = session.get("profile")
    if not questions or not profile:
        flash("Please upload your resume to start an interview.", "error")
        return redirect(url_for("index"))

    mode = session.get("mode", "mcq")
    # Never send the answer key to the client.
    safe_questions = []
    for q in questions:
        safe_q = {"id": q["id"], "question": q["question"], "topic": q.get("topic", "")}
        if mode == "mcq":
            safe_q["options"] = q.get("options", {})
        safe_questions.append(safe_q)

    seconds_per_q = QUESTION_TIME_SECONDS.get(session.get("difficulty", "Adaptive"), 90)

    return render_template(
        "interview.html",
        questions=safe_questions,
        mode=mode,
        profile=profile,
        seconds_per_q=seconds_per_q,
        round_num=session.get("round", 1),
    )


@app.route("/submit", methods=["POST"])
def submit():
    questions = session.get("questions")
    profile = session.get("profile")
    mode = session.get("mode", "mcq")
    if not questions or not profile:
        return jsonify({"error": "No active interview session."}), 400

    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers", {})

    try:
        result = groq_service.evaluate_answers(profile, questions, answers, mode)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    # attach the underlying question text/options for the results page
    result["questions"] = questions
    result["answers"] = answers
    result["mode"] = mode
    result["timestamp"] = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    result["round"] = session.get("round", 1)

    session["results"] = result

    history = session.get("history", [])
    history.append({
        "timestamp": result["timestamp"],
        "overall_score_percent": result["overall_score_percent"],
        "performance_rating": result["performance_rating"],
        "correct_count": result["correct_count"],
        "incorrect_count": result["incorrect_count"],
        "round": result["round"],
        "domain": profile.get("primary_domain"),
    })
    session["history"] = history[-20:]

    return jsonify({"redirect": url_for("results")})


@app.route("/results")
def results():
    result = session.get("results")
    profile = session.get("profile")
    if not result or not profile:
        flash("No interview results yet — start a new interview first.", "error")
        return redirect(url_for("index"))
    return render_template("results.html", result=result, profile=profile,
                            resume_filename=session.get("resume_filename", "resume.pdf"))


@app.route("/generate-more", methods=["POST"])
def generate_more():
    profile = session.get("profile")
    mode = session.get("mode", "mcq")
    difficulty = session.get("difficulty", "Adaptive")
    asked = session.get("asked_questions", [])

    if not profile:
        flash("Please upload your resume to start an interview.", "error")
        return redirect(url_for("index"))

    try:
        questions = groq_service.generate_questions(
            profile, mode, difficulty, avoid_questions=asked
        )
    except Exception as exc:
        flash(f"Could not generate more questions: {exc}", "error")
        return redirect(url_for("results"))

    session["questions"] = questions
    session["asked_questions"] = asked + [q["question"] for q in questions]
    session["round"] = session.get("round", 1) + 1
    session.pop("results", None)

    return redirect(url_for("interview"))


# --------------------------------------------------------------------------- #
# History (bonus feature)
# --------------------------------------------------------------------------- #
@app.route("/history")
def history():
    return render_template("history.html", history=session.get("history", []))


# --------------------------------------------------------------------------- #
# Downloadable PDF report (bonus feature)
# --------------------------------------------------------------------------- #
@app.route("/download-report")
def download_report():
    result = session.get("results")
    profile = session.get("profile")
    if not result or not profile:
        flash("No interview results available to download.", "error")
        return redirect(url_for("index"))

    pdf_bytes = build_pdf_report(profile, result)
    filename = f"interview_report_{uuid.uuid4().hex[:8]}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


def build_pdf_report(profile: dict, result: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()

    dark_green = colors.HexColor("#0B3D2E")
    blue = colors.HexColor("#144272")

    title_style = ParagraphStyle("Title2", parent=styles["Title"], textColor=dark_green)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=blue, spaceBefore=14)
    body = styles["BodyText"]

    story = [
        Paragraph("AI Resume-Based Interview Simulator", title_style),
        Paragraph("Interview Performance Report", styles["Heading3"]),
        Spacer(1, 10),
        Paragraph(f"Candidate: {profile.get('candidate_name', 'Candidate')}", body),
        Paragraph(f"Domain: {profile.get('primary_domain', '-')}", body),
        Paragraph(f"Date: {result.get('timestamp', '-')}", body),
        Spacer(1, 12),
        Paragraph("Overall Result", h2),
    ]

    summary_table = Table([
        ["Overall Score", f"{result.get('overall_score_percent')}%"],
        ["Performance Rating", result.get("performance_rating", "-")],
        ["Correct Answers", f"{result.get('correct_count')} / {len(result.get('questions', []))}"],
        ["Incorrect Answers", f"{result.get('incorrect_count')} / {len(result.get('questions', []))}"],
    ], colWidths=[180, 200])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2E1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F6F4")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Summary Feedback", h2))
    story.append(Paragraph(result.get("summary_feedback", ""), body))

    story.append(Paragraph("Strengths", h2))
    for s in result.get("strengths", []):
        story.append(Paragraph(f"• {s}", body))

    story.append(Paragraph("Weaknesses", h2))
    for w in result.get("weaknesses", []):
        story.append(Paragraph(f"• {w}", body))

    story.append(Paragraph("AI Recommendations", h2))
    for r in result.get("recommendations", []):
        story.append(Paragraph(f"• {r}", body))

    story.append(Paragraph("Question-by-Question Breakdown", h2))
    q_rows = [["#", "Question", "Result", "Score"]]
    per_q = {pq["id"]: pq for pq in result.get("per_question", [])}
    for q in result.get("questions", []):
        pq = per_q.get(q["id"], {})
        q_rows.append([
            str(q["id"]),
            Paragraph(q["question"], body),
            "Correct" if pq.get("is_correct") else "Incorrect",
            str(pq.get("score", "-")),
        ])
    q_table = Table(q_rows, colWidths=[20, 300, 60, 50])
    q_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E2E1")),
        ("BACKGROUND", (0, 0), (-1, 0), dark_green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(q_table)

    doc.build(story)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# New interview (clears session)
# --------------------------------------------------------------------------- #
@app.route("/new-interview")
def new_interview():
    keep_history = session.get("history", [])
    session.clear()
    session["history"] = keep_history
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)

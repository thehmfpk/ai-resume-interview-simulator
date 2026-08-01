"""
groq_service.py
----------------
Two independent Groq-powered pipelines, exactly as required by the spec:

  MODEL 1 - Interview Question Generator
      - analyze_resume()   -> domain / skills / projects / technologies
      - generate_questions() -> exactly 10 personalised interview questions

  MODEL 2 - Interview Evaluator
      - evaluate_answers() -> per-question scoring + AI feedback + overall report

Both pipelines call the Groq chat-completions endpoint independently so they
can be swapped, tuned or scaled without affecting one another.
"""

import os
import json
import re
from groq import Groq

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

_client = None


def get_client():
    """Lazily build the Groq client so a missing key fails at call-time,
    not at import-time (keeps the Flask app importable for testing)."""
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        _client = Groq(api_key=api_key)
    return _client


def _extract_json(raw: str):
    """Groq sometimes wraps JSON in prose or code fences even when asked
    not to. Pull the first {...} or [...] block out defensively."""
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw.strip(), flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw.strip()).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{.*\}|\[.*\])", raw, flags=re.DOTALL)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"Could not parse JSON from model output: {raw[:300]}")


def _chat(system_prompt: str, user_prompt: str, temperature: float = 0.4):
    client = get_client()
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=temperature,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return completion.choices[0].message.content


# --------------------------------------------------------------------------- #
# MODEL 1a — Resume analysis / domain detection
# --------------------------------------------------------------------------- #
def analyze_resume(resume_text: str) -> dict:
    system_prompt = (
        "You are a precise resume-analysis engine used inside an interview "
        "simulator. You read raw resume text and extract structured facts "
        "about the candidate. You NEVER invent skills, projects or "
        "technologies that are not evidenced in the text. "
        "Respond with ONLY valid JSON, no commentary, no markdown fences."
    )
    user_prompt = f"""
Analyse the resume text below and return a JSON object with EXACTLY this shape:

{{
  "candidate_name": "string or 'Candidate' if not found",
  "primary_domain": "one of: Artificial Intelligence, Data Science, Web Development, Mobile Development, DevOps, Cybersecurity, Cloud Engineering, Software Engineering, Other",
  "seniority_level": "Entry-level | Junior | Mid-level | Senior",
  "skills": ["list", "of", "technical", "skills"],
  "technologies": ["list", "of", "tools/frameworks/languages"],
  "projects": [
    {{"name": "project name", "description": "one line description", "technologies": ["tech1","tech2"]}}
  ],
  "summary": "2-3 sentence professional summary of the candidate"
}}

Resume text:
\"\"\"{resume_text[:9000]}\"\"\"
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.2)
    return _extract_json(raw)


# --------------------------------------------------------------------------- #
# MODEL 1b — Question generation
# --------------------------------------------------------------------------- #
def generate_questions(profile: dict, mode: str, difficulty: str = "Adaptive",
                        avoid_questions=None) -> list:
    """mode: 'mcq' or 'qna'. Returns a list of exactly 10 question dicts."""
    avoid_questions = avoid_questions or []

    system_prompt = (
        "You are an expert technical interviewer. You generate interview "
        "questions based ONLY on the candidate's actual resume content "
        "(their listed skills, projects and technologies). Never ask about "
        "technologies the candidate did not mention. Keep a balanced mix of "
        "difficulty. Respond with ONLY valid JSON — a JSON array — no "
        "commentary, no markdown fences."
    )

    if mode == "mcq":
        shape = """[
  {
    "id": 1,
    "question": "string",
    "options": {"A": "string", "B": "string", "C": "string", "D": "string"},
    "correct_answer": "A|B|C|D",
    "topic": "short topic tag, e.g. 'Python' or 'Machine Learning'",
    "difficulty": "Easy|Medium|Hard"
  }
]"""
    else:
        shape = """[
  {
    "id": 1,
    "question": "string",
    "expected_answer": "concise ideal answer used only for grading, 2-4 sentences",
    "topic": "short topic tag",
    "difficulty": "Easy|Medium|Hard"
  }
]"""

    avoid_block = ""
    if avoid_questions:
        joined = "\n".join(f"- {q}" for q in avoid_questions[:40])
        avoid_block = f"\nDo NOT repeat or closely rephrase any of these previously asked questions:\n{joined}\n"

    user_prompt = f"""
Candidate profile (extracted from resume):
{json.dumps(profile, indent=2)}

Generate EXACTLY 10 interview questions in "{mode}" format at "{difficulty}" difficulty,
based ONLY on the candidate's domain ({profile.get('primary_domain')}), skills,
projects and technologies above. Do not ask unrelated questions.
{avoid_block}
Return a JSON array of exactly 10 objects shaped like:
{shape}
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.6)
    questions = _extract_json(raw)
    if not isinstance(questions, list):
        raise ValueError("Question generator did not return a list")
    for i, q in enumerate(questions, start=1):
        q["id"] = i
    return questions[:10]


# --------------------------------------------------------------------------- #
# MODEL 2 — Answer evaluation
# --------------------------------------------------------------------------- #
def _rating_from_percent(pct: float) -> str:
    if pct >= 90:
        return "Excellent"
    if pct >= 75:
        return "Very Good"
    if pct >= 60:
        return "Good"
    if pct >= 40:
        return "Fair"
    return "Needs Improvement"


def evaluate_answers(profile: dict, questions: list, answers: dict, mode: str) -> dict:
    """
    answers: {question_id(str): candidate_answer(str)}
    Returns the full results-dashboard payload.

    IMPORTANT: for MCQ, correctness is decided by exact string comparison in
    Python — never by the LLM. LLMs are not reliable at exact-match judgment,
    so letting the model "decide" correctness produced inconsistent scores
    regardless of the candidate's actual selections. Groq is only used here
    to write qualitative feedback around numbers that are already final.
    """
    if mode == "mcq":
        return _evaluate_mcq(profile, questions, answers)
    return _evaluate_qna(profile, questions, answers)


def _evaluate_mcq(profile: dict, questions: list, answers: dict) -> dict:
    per_question = []
    correct_count = 0

    for q in questions:
        qid = str(q["id"])
        candidate_letter = (answers.get(qid) or "").strip().upper()
        correct_letter = (q.get("correct_answer") or "").strip().upper()
        is_correct = bool(candidate_letter) and candidate_letter == correct_letter
        if is_correct:
            correct_count += 1
        per_question.append({
            "id": q["id"],
            "is_correct": is_correct,
            "score": 10 if is_correct else 0,
            "candidate_letter": candidate_letter or "(no answer)",
            "correct_letter": correct_letter,
        })

    total = len(questions) or 1
    incorrect_count = total - correct_count
    overall_score_percent = round((correct_count / total) * 100)
    performance_rating = _rating_from_percent(overall_score_percent)

    narrative = _generate_narrative_feedback(
        profile, questions, per_question, correct_count, incorrect_count,
        overall_score_percent, performance_rating, mode="mcq",
    )

    # merge the LLM's per-question feedback text into our deterministic scores
    fb_by_id = {f["id"]: f.get("feedback", "") for f in narrative.get("per_question_feedback", [])}
    for pq in per_question:
        pq["feedback"] = fb_by_id.get(pq["id"], "Correct — well matched to your resume." if pq["is_correct"]
                                       else "Incorrect — review this topic.")

    return {
        "per_question": per_question,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "overall_score_percent": overall_score_percent,
        "performance_rating": performance_rating,
        "strengths": narrative.get("strengths", []),
        "weaknesses": narrative.get("weaknesses", []),
        "recommendations": narrative.get("recommendations", []),
        "summary_feedback": narrative.get("summary_feedback", ""),
    }


def _evaluate_qna(profile: dict, questions: list, answers: dict) -> dict:
    system_prompt = (
        "You are a rigorous but fair technical interview evaluator. You "
        "judge free-text answers against an expected-answer rubric, score "
        "each response out of 10, and mark is_correct true only if the "
        "candidate's answer genuinely captures the key concept of the "
        "expected answer (partial/vague/off-topic answers are is_correct: "
        "false even if score > 0). An empty answer is always incorrect with "
        "score 0. Respond with ONLY valid JSON, no commentary, no markdown "
        "fences."
    )

    graded_material = []
    for q in questions:
        qid = str(q["id"])
        graded_material.append({
            "id": q["id"],
            "question": q["question"],
            "topic": q.get("topic", ""),
            "expected_answer": q.get("expected_answer", ""),
            "candidate_answer": answers.get(qid, "") or "(no answer given)",
        })

    user_prompt = f"""
Candidate profile:
{json.dumps(profile, indent=2)}

Grade each of these free-text answers against its expected_answer.

Data:
{json.dumps(graded_material, indent=2)}

Return ONLY a JSON object with EXACTLY this shape:
{{
  "per_question": [
    {{"id": 1, "is_correct": true, "score": 8.5, "feedback": "one or two sentence specific feedback"}}
  ],
  "strengths": ["short phrase", "short phrase", "short phrase"],
  "weaknesses": ["short phrase", "short phrase"],
  "recommendations": ["actionable suggestion", "actionable suggestion", "actionable suggestion"],
  "summary_feedback": "3-4 sentence overall narrative feedback for the candidate"
}}
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.2)
    result = _extract_json(raw)

    per_question = result.get("per_question", [])
    total = len(questions) or 1
    # Recompute counts ourselves too, don't fully trust the model's own tallies.
    correct_count = sum(1 for pq in per_question if pq.get("is_correct"))
    incorrect_count = total - correct_count
    overall_score_percent = round((correct_count / total) * 100)

    return {
        "per_question": per_question,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "overall_score_percent": overall_score_percent,
        "performance_rating": _rating_from_percent(overall_score_percent),
        "strengths": result.get("strengths", []),
        "weaknesses": result.get("weaknesses", []),
        "recommendations": result.get("recommendations", []),
        "summary_feedback": result.get("summary_feedback", ""),
    }


def _generate_narrative_feedback(profile, questions, per_question, correct_count,
                                  incorrect_count, overall_score_percent,
                                  performance_rating, mode) -> dict:
    """Used only for MCQ mode: asks Groq for qualitative write-up AFTER
    correctness/scores are already finalized deterministically. The model
    cannot change any number here, only describe it."""
    system_prompt = (
        "You are an interview coach writing qualitative feedback. You are "
        "given the FINAL, ALREADY-DECIDED scores for an interview — you do "
        "not decide correctness, you only explain and advise based on the "
        "given facts. Respond with ONLY valid JSON, no commentary, no "
        "markdown fences."
    )

    qmap = {q["id"]: q for q in questions}
    detail = []
    for pq in per_question:
        q = qmap[pq["id"]]
        detail.append({
            "id": pq["id"],
            "question": q["question"],
            "topic": q.get("topic", ""),
            "is_correct": pq["is_correct"],
            "candidate_selected": pq["candidate_letter"],
            "correct_option": pq["correct_letter"],
            "correct_option_text": q.get("options", {}).get(pq["correct_letter"], ""),
        })

    user_prompt = f"""
Candidate profile:
{json.dumps(profile, indent=2)}

Final results (already decided, do not change):
- Correct: {correct_count}, Incorrect: {incorrect_count}
- Overall score: {overall_score_percent}%
- Rating: {performance_rating}

Per-question detail:
{json.dumps(detail, indent=2)}

Return ONLY a JSON object with EXACTLY this shape:
{{
  "per_question_feedback": [
    {{"id": 1, "feedback": "one short sentence explaining this specific result"}}
  ],
  "strengths": ["short phrase", "short phrase", "short phrase"],
  "weaknesses": ["short phrase", "short phrase"],
  "recommendations": ["actionable suggestion", "actionable suggestion", "actionable suggestion"],
  "summary_feedback": "3-4 sentence overall narrative feedback consistent with the {overall_score_percent}% score"
}}
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.4)
    return _extract_json(raw)

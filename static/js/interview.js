(function () {
  const data = window.INTERVIEW_DATA;
  const questions = data.questions;
  const mode = data.mode;
  const totalTime = data.secondsPerQ;
  const RADIUS = 27;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

  let current = 0;
  const answers = {}; // { questionId: answerValue }
  let timeLeft = totalTime;
  let timerInterval = null;

  const questionText = document.getElementById("questionText");
  const questionTopic = document.getElementById("questionTopic");
  const answerArea = document.getElementById("answerArea");
  const qCurrent = document.getElementById("qCurrent");
  const progressFill = document.getElementById("progressFill");
  const dotTrack = document.getElementById("dotTrack");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const timerCircle = document.getElementById("timerCircle");
  const timerLabel = document.getElementById("timerLabel");
  const timerRing = document.getElementById("timerRing");
  const questionCard = document.getElementById("questionCard");
  const submitOverlay = document.getElementById("submitOverlay");

  timerCircle.style.strokeDasharray = `${CIRCUMFERENCE} ${CIRCUMFERENCE}`;

  function buildDots() {
    dotTrack.innerHTML = "";
    questions.forEach((_, i) => {
      const d = document.createElement("div");
      d.className = "dot";
      dotTrack.appendChild(d);
    });
  }

  function updateDots() {
    const dots = dotTrack.querySelectorAll(".dot");
    dots.forEach((d, i) => {
      d.classList.remove("current", "answered");
      const q = questions[i];
      if (answers[q.id] !== undefined && answers[q.id] !== "") d.classList.add("answered");
      if (i === current) d.classList.add("current");
    });
  }

  function renderQuestion() {
    const q = questions[current];
    questionTopic.textContent = q.topic || "General";
    questionText.textContent = q.question;
    answerArea.innerHTML = "";

    if (mode === "mcq") {
      const list = document.createElement("div");
      list.className = "option-list";
      Object.entries(q.options || {}).forEach(([key, val]) => {
        const item = document.createElement("div");
        item.className = "option-item" + (answers[q.id] === key ? " selected" : "");
        item.innerHTML = `<div class="option-key">${key}</div><div class="option-text">${val}</div>`;
        item.addEventListener("click", () => {
          answers[q.id] = key;
          renderQuestion();
          updateDots();
        });
        list.appendChild(item);
      });
      answerArea.appendChild(list);
    } else {
      const textarea = document.createElement("textarea");
      textarea.className = "answer-box";
      textarea.placeholder = "Type your answer here…";
      textarea.value = answers[q.id] || "";
      textarea.addEventListener("input", () => {
        answers[q.id] = textarea.value;
        updateDots();
      });
      answerArea.appendChild(textarea);
    }

    qCurrent.textContent = current + 1;
    progressFill.style.width = `${((current + 1) / questions.length) * 100}%`;
    prevBtn.disabled = current === 0;
    nextBtn.textContent = current === questions.length - 1 ? "Submit Interview" : "Next →";
    updateDots();
    resetTimer();
  }

  function setRing(t) {
    const fraction = Math.max(t, 0) / totalTime;
    const offset = CIRCUMFERENCE * (1 - fraction);
    timerCircle.style.strokeDashoffset = offset;
    timerLabel.textContent = Math.max(t, 0);
    timerRing.classList.toggle("low", t <= 10);
  }

  function resetTimer() {
    clearInterval(timerInterval);
    timeLeft = totalTime;
    setRing(timeLeft);
    timerInterval = setInterval(() => {
      timeLeft -= 1;
      setRing(timeLeft);
      if (timeLeft <= 0) {
        clearInterval(timerInterval);
        goNext(true);
      }
    }, 1000);
  }

  function goNext(auto) {
    if (current < questions.length - 1) {
      current += 1;
      renderQuestion();
    } else {
      submitInterview();
    }
  }

  function goPrev() {
    if (current > 0) {
      current -= 1;
      renderQuestion();
    }
  }

  function submitInterview() {
    clearInterval(timerInterval);
    questionCard.style.display = "none";
    document.querySelector(".interview-nav").style.display = "none";
    submitOverlay.style.display = "block";

    fetch(data.submitUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    })
      .then((res) => res.json())
      .then((json) => {
        if (json.redirect) {
          window.location.href = json.redirect;
        } else {
          throw new Error(json.error || "Evaluation failed");
        }
      })
      .catch((err) => {
        submitOverlay.innerHTML = `<p style="color:var(--danger)">Something went wrong: ${err.message}. Please try submitting again.</p>
          <button class="btn btn-primary" onclick="location.reload()">Reload</button>`;
      });
  }

  nextBtn.addEventListener("click", () => goNext(false));
  prevBtn.addEventListener("click", goPrev);

  buildDots();
  renderQuestion();
})();

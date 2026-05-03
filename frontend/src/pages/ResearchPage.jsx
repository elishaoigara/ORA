import { useState, useRef, useEffect } from "react"
import BASE_URL from "../api"

const R = BASE_URL + "/api/research"

async function api(method, path, body = null, timeout = 90000) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), timeout)
  try {
    const opts = { method, signal: ctrl.signal, headers: { "Content-Type": "application/json" } }
    if (body) opts.body = JSON.stringify(body)
    const res = await fetch(R + path, opts)
    clearTimeout(t)
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "HTTP " + res.status) }
    return res.json()
  } catch (e) { clearTimeout(t); throw e }
}

// ── Markdown renderer ──────────────────────────────────────────
function Md({ text }) {
  if (!text) return null
  const html = text
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/^### (.+)$/gm,"<h3>$1</h3>")
    .replace(/^## (.+)$/gm,"<h2>$1</h2>")
    .replace(/^# (.+)$/gm,"<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>")
    .replace(/\*(.+?)\*/g,"<em>$1</em>")
    .replace(/`(.+?)`/g,"<code>$1</code>")
    .replace(/^> (.+)$/gm,"<blockquote>$1</blockquote>")
    .replace(/^[-*] (.+)$/gm,"<li>$1</li>")
    .replace(/(<li>[\s\S]+?<\/li>)/g,"<ul>$1</ul>")
    .replace(/\n\n/g,"</p><p>")
    .replace(/^(?!<[hpulbi])(.+)$/gm,"<p>$1</p>")
    .replace(/<p><\/p>/g,"")
  return <div className="result-content" dangerouslySetInnerHTML={{ __html: html }} />
}

// ── Mode definitions ────────────────────────────────────────────
const MODES = [
  { id:"research",    icon:"⊕", label:"Research",     desc:"Web search & synthesis" },
  { id:"explain",     icon:"◎", label:"Explain",       desc:"Any concept, any level" },
  { id:"quiz",        icon:"◆", label:"Quiz Me",       desc:"Test your knowledge" },
  { id:"flashcards",  icon:"▣", label:"Flashcards",    desc:"Spaced repetition cards" },
  { id:"summarize",   icon:"≡", label:"Summarize",     desc:"Paste text, get notes" },
  { id:"study-plan",  icon:"◈", label:"Study Plan",    desc:"Personalised schedule" },
  { id:"essay",       icon:"✎", label:"Essay",         desc:"Long-form writing" },
  { id:"presentation",icon:"◧", label:"Slides",        desc:"Presentation outline" },
]

const SUGGESTIONS = {
  research:    ["How does machine learning work?","Kenya's economic outlook 2025","React vs Vue vs Angular","Climate change in East Africa","History of the internet"],
  explain:     ["Photosynthesis","The French Revolution","How neural networks learn","Calculus derivatives","Supply and demand"],
  quiz:        ["World War II","Basic algebra","Cell biology","Python programming","The water cycle"],
  flashcards:  ["Spanish vocabulary","Human anatomy","Programming data structures","Chemical elements","African capitals"],
  summarize:   [],
  "study-plan":["Mathematics","Biology","Computer Science","History","Chemistry"],
  essay:       ["Impact of social media on society","The future of AI","Climate change solutions","Importance of education"],
  presentation:["Introduction to Python","Climate Change","My Business Idea","The Solar System"],
}

const LOAD_MSGS = {
  research:    ["Searching the web…","Reading sources…","Synthesising findings…"],
  explain:     ["Understanding your question…","Building explanation…","Adding examples…"],
  quiz:        ["Crafting questions…","Setting difficulty…","Verifying answers…"],
  flashcards:  ["Identifying key concepts…","Writing cards…","Adding hints…"],
  summarize:   ["Reading text…","Extracting key points…","Formatting notes…"],
  "study-plan":["Analysing subject…","Building schedule…","Adding resources…"],
  essay:       ["Outlining structure…","Writing draft…","Polishing prose…"],
  presentation:["Planning slides…","Writing content…","Structuring deck…"],
}

// ── Quiz component ──────────────────────────────────────────────
function QuizRunner({ data, onRetry }) {
  const [answers,   setAnswers]   = useState({})
  const [revealed,  setRevealed]  = useState({})
  const [submitted, setSubmitted] = useState(false)
  const [score,     setScore]     = useState(null)

  if (!data?.questions?.length) return (
    <div className="empty-state">
      <div className="empty-icon">◆</div>
      <div className="empty-title">No questions generated</div>
      <div className="empty-body">Try a different topic or difficulty</div>
    </div>
  )

  const submit = () => {
    let correct = 0
    data.questions.forEach(q => {
      if ((answers[q.id] || "").toUpperCase() === (q.answer || "").toUpperCase()) correct++
    })
    setScore(correct)
    setSubmitted(true)
    setRevealed(Object.fromEntries(data.questions.map(q => [q.id, true])))
  }

  const pct = score !== null ? Math.round((score / data.questions.length) * 100) : null
  const grade = pct === null ? "" : pct >= 80 ? "🎉 Excellent!" : pct >= 60 ? "👍 Good work" : "📚 Keep studying"

  return (
    <div>
      {/* Score banner */}
      {submitted && (
        <div style={{
          padding:"14px 16px", borderRadius:"var(--radius)", marginBottom:16,
          background: pct >= 80 ? "rgba(0,255,157,0.08)" : pct >= 60 ? "rgba(255,153,0,0.08)" : "rgba(255,68,68,0.08)",
          border: `1px solid ${pct >= 80 ? "rgba(0,255,157,0.3)" : pct >= 60 ? "rgba(255,153,0,0.3)" : "rgba(255,68,68,0.3)"}`,
          display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:8,
        }}>
          <div>
            <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text-4)", letterSpacing:2, marginBottom:4 }}>SCORE</div>
            <div style={{ fontFamily:"var(--mono)", fontSize:28, fontWeight:700,
              color: pct >= 80 ? "var(--green)" : pct >= 60 ? "var(--orange)" : "var(--red)" }}>
              {score}/{data.questions.length} <span style={{ fontSize:14 }}>({pct}%)</span>
            </div>
            <div style={{ fontSize:13, color:"var(--text-2)", marginTop:4 }}>{grade}</div>
          </div>
          <button className="btn" onClick={onRetry}>↺ NEW QUIZ</button>
        </div>
      )}

      {/* Questions */}
      {data.questions.map((q, idx) => {
        const userAns   = answers[q.id] || ""
        const isCorrect = submitted && userAns.toUpperCase() === (q.answer || "").toUpperCase()
        const isWrong   = submitted && userAns && !isCorrect
        return (
          <div key={q.id} style={{
            background:"var(--bg-card)", border:`1px solid ${submitted ? (isCorrect ? "rgba(0,255,157,0.3)" : isWrong ? "rgba(255,68,68,0.3)" : "var(--border)") : "var(--border)"}`,
            borderRadius:"var(--radius-lg)", padding:"14px 16px", marginBottom:10,
          }}>
            <div style={{ display:"flex", gap:8, marginBottom:10 }}>
              <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text-5)", minWidth:20 }}>Q{idx+1}</span>
              <div style={{ fontSize:13, color:"var(--text-1)", lineHeight:1.5, flex:1 }}>{q.question}</div>
            </div>

            {/* MCQ / True-False options */}
            {q.type !== "short_answer" && q.options && Object.keys(q.options).length > 0 && (
              <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                {Object.entries(q.options).map(([key, val]) => {
                  const isSelected  = userAns === key
                  const isAnswer    = submitted && key === q.answer
                  const isUserWrong = submitted && isSelected && key !== q.answer
                  return (
                    <button key={key} disabled={submitted} onClick={() => setAnswers(a => ({...a,[q.id]:key}))}
                      style={{
                        display:"flex", alignItems:"center", gap:10,
                        background: isAnswer ? "rgba(0,255,157,0.1)" : isUserWrong ? "rgba(255,68,68,0.1)" : isSelected ? "rgba(255,153,0,0.1)" : "var(--bg-2)",
                        border:`1px solid ${isAnswer ? "rgba(0,255,157,0.4)" : isUserWrong ? "rgba(255,68,68,0.4)" : isSelected ? "rgba(255,153,0,0.4)" : "var(--border)"}`,
                        borderRadius:"var(--radius)", padding:"8px 12px", cursor: submitted ? "default" : "pointer",
                        textAlign:"left", transition:"all 0.15s",
                      }}>
                      <span style={{ fontFamily:"var(--mono)", fontSize:11, fontWeight:700, minWidth:18,
                        color: isAnswer ? "var(--green)" : isUserWrong ? "var(--red)" : "var(--text-4)" }}>{key}</span>
                      <span style={{ fontSize:12, color:"var(--text-2)" }}>{val}</span>
                      {isAnswer    && <span style={{ marginLeft:"auto", color:"var(--green)" }}>✓</span>}
                      {isUserWrong && <span style={{ marginLeft:"auto", color:"var(--red)" }}>✗</span>}
                    </button>
                  )
                })}
              </div>
            )}

            {/* Short answer */}
            {q.type === "short_answer" && (
              <div>
                <textarea disabled={submitted} value={answers[q.id] || ""}
                  onChange={e => setAnswers(a => ({...a,[q.id]:e.target.value}))}
                  placeholder="Type your answer..." rows={2}
                  style={{
                    width:"100%", background:"var(--bg-2)", border:"1px solid var(--border-2)",
                    borderRadius:"var(--radius)", padding:"8px 12px", color:"var(--text-1)",
                    fontSize:12, fontFamily:"inherit", resize:"vertical", boxSizing:"border-box",
                  }}
                />
                {submitted && (
                  <div style={{ marginTop:6, padding:"6px 10px", background:"rgba(0,255,157,0.06)",
                    border:"1px solid rgba(0,255,157,0.2)", borderRadius:"var(--radius)", fontSize:12, color:"var(--text-2)" }}>
                    <span style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--green)", letterSpacing:1 }}>MODEL ANSWER: </span>
                    {q.answer}
                  </div>
                )}
              </div>
            )}

            {/* Explanation */}
            {revealed[q.id] && q.explanation && (
              <div style={{ marginTop:8, paddingTop:8, borderTop:"1px solid var(--border)",
                fontSize:11, color:"var(--text-3)", lineHeight:1.5, fontStyle:"italic" }}>
                💡 {q.explanation}
              </div>
            )}

            {/* Reveal hint for unanswered */}
            {!submitted && !revealed[q.id] && (
              <button className="btn btn-sm" style={{ marginTop:8, opacity:0.6 }}
                onClick={() => setRevealed(r => ({...r,[q.id]:true}))}>
                💡 HINT
              </button>
            )}
          </div>
        )
      })}

      {!submitted ? (
        <button className="btn btn-green" style={{ width:"100%", justifyContent:"center", padding:12 }}
          onClick={submit} disabled={Object.keys(answers).length === 0}>
          ◆ SUBMIT QUIZ
        </button>
      ) : (
        <div style={{ display:"flex", gap:8 }}>
          <button className="btn" style={{ flex:1, justifyContent:"center" }} onClick={onRetry}>↺ NEW QUIZ</button>
          <button className="btn btn-green" style={{ flex:1, justifyContent:"center" }}
            onClick={() => { setAnswers({}); setRevealed({}); setSubmitted(false); setScore(null) }}>
            ↺ RETRY SAME
          </button>
        </div>
      )}
    </div>
  )
}

// ── Flashcard component ─────────────────────────────────────────
function FlashcardDeck({ data, onRetry }) {
  const [idx,      setIdx]      = useState(0)
  const [flipped,  setFlipped]  = useState(false)
  const [known,    setKnown]    = useState(new Set())
  const [unknown,  setUnknown]  = useState(new Set())
  const [done,     setDone]     = useState(false)

  const cards = data?.cards || []
  if (!cards.length) return <div className="empty-state"><div className="empty-title">No cards generated</div></div>

  const card = cards[idx]
  const total = cards.length

  const next = (result) => {
    if (result === "know")    setKnown(s => new Set([...s, idx]))
    if (result === "unknown") setUnknown(s => new Set([...s, idx]))
    setFlipped(false)
    if (idx + 1 >= total) { setDone(true) }
    else { setTimeout(() => setIdx(i => i + 1), 120) }
  }

  if (done) {
    const knownPct = Math.round((known.size / total) * 100)
    return (
      <div style={{ textAlign:"center", padding:"24px 0" }}>
        <div style={{ fontSize:48, marginBottom:12 }}>🎓</div>
        <div style={{ fontFamily:"var(--mono)", fontSize:28, fontWeight:700, color:"var(--green)", marginBottom:4 }}>
          {known.size}/{total}
        </div>
        <div style={{ fontSize:13, color:"var(--text-2)", marginBottom:20 }}>cards mastered ({knownPct}%)</div>
        {unknown.size > 0 && (
          <div style={{ background:"rgba(255,153,0,0.08)", border:"1px solid rgba(255,153,0,0.2)",
            borderRadius:"var(--radius)", padding:"10px 14px", marginBottom:16, fontSize:12, color:"var(--orange)" }}>
            ⚠ {unknown.size} card(s) need more review
          </div>
        )}
        <div style={{ display:"flex", gap:8, justifyContent:"center" }}>
          <button className="btn" onClick={() => { setIdx(0); setFlipped(false); setKnown(new Set()); setUnknown(new Set()); setDone(false) }}>
            ↺ RESTART DECK
          </button>
          {unknown.size > 0 && (
            <button className="btn btn-green" onClick={() => {
              // Study only unknown cards
              const unknownArr = [...unknown]
              setIdx(unknownArr[0])
              setFlipped(false); setKnown(new Set()); setUnknown(new Set()); setDone(false)
            }}>
              📚 REVIEW MISSED
            </button>
          )}
          <button className="btn" onClick={onRetry}>⊕ NEW DECK</button>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Progress */}
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:14 }}>
        <div style={{ flex:1, height:4, background:"var(--border)", borderRadius:2, overflow:"hidden" }}>
          <div style={{ height:"100%", background:"var(--green)", borderRadius:2, width:`${((idx)/total)*100}%`, transition:"width 0.3s" }} />
        </div>
        <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text-4)", minWidth:40 }}>{idx+1}/{total}</span>
        <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--green)" }}>✓{known.size}</span>
        <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--orange)" }}>✗{unknown.size}</span>
      </div>

      {/* Card */}
      <div
        onClick={() => setFlipped(f => !f)}
        style={{
          background: flipped ? "rgba(0,255,157,0.05)" : "var(--bg-card)",
          border: `1px solid ${flipped ? "rgba(0,255,157,0.3)" : "var(--border)"}`,
          borderRadius:"var(--radius-lg)", padding:"32px 20px",
          minHeight:180, cursor:"pointer", transition:"all 0.2s",
          display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
          textAlign:"center", gap:12, marginBottom:14,
          userSelect:"none",
        }}
      >
        <div style={{ fontFamily:"var(--mono)", fontSize:9, color: flipped ? "var(--green)" : "var(--text-5)",
          letterSpacing:3, marginBottom:8 }}>
          {flipped ? "▼ ANSWER" : "▲ QUESTION — TAP TO FLIP"}
        </div>
        <div style={{ fontSize:15, fontWeight: flipped ? 400 : 600, color:"var(--text-1)", lineHeight:1.5, maxWidth:500 }}>
          {flipped ? card.back : card.front}
        </div>
        {flipped && card.hint && (
          <div style={{ fontSize:11, color:"var(--text-4)", fontStyle:"italic", marginTop:4 }}>
            💡 {card.hint}
          </div>
        )}
        {!flipped && (
          <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text-5)", marginTop:8 }}>TAP TO REVEAL</div>
        )}
      </div>

      {/* Know / Don't know */}
      {flipped ? (
        <div style={{ display:"flex", gap:10 }}>
          <button className="btn btn-red" style={{ flex:1, justifyContent:"center", padding:12 }}
            onClick={() => next("unknown")}>
            ✗ STILL LEARNING
          </button>
          <button className="btn btn-green" style={{ flex:1, justifyContent:"center", padding:12 }}
            onClick={() => next("know")}>
            ✓ GOT IT
          </button>
        </div>
      ) : (
        <div style={{ display:"flex", gap:8, justifyContent:"center" }}>
          <button className="btn btn-sm" onClick={() => setIdx(i => Math.max(0, i-1))} disabled={idx === 0}>← PREV</button>
          <button className="btn btn-sm" onClick={() => setFlipped(true)}>FLIP CARD</button>
          <button className="btn btn-sm" onClick={() => next("skip")}>SKIP →</button>
        </div>
      )}
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────
export default function ResearchPage() {
  const [mode,       setMode]       = useState("research")
  const [query,      setQuery]      = useState("")
  const [pasteText,  setPasteText]  = useState("")
  const [loading,    setLoading]    = useState(false)
  const [loadStep,   setLoadStep]   = useState(0)
  const [result,     setResult]     = useState(null)
  const [quizData,   setQuizData]   = useState(null)
  const [cardData,   setCardData]   = useState(null)
  const [toast,      setToast]      = useState(null)
  const [history,    setHistory]    = useState([])
  const [showHist,   setShowHist]   = useState(false)
  // Mode-specific options
  const [quizNum,    setQuizNum]    = useState(5)
  const [quizDiff,   setQuizDiff]   = useState("medium")
  const [quizStyle,  setQuizStyle]  = useState("mcq")
  const [cardNum,    setCardNum]    = useState(10)
  const [explainLvl, setExplainLvl] = useState("beginner")
  const [sumStyle,   setSumStyle]   = useState("bullet")
  const [sumLen,     setSumLen]     = useState("medium")
  const [planDate,   setPlanDate]   = useState("2 weeks")
  const [planHours,  setPlanHours]  = useState(2)
  const [planLevel,  setPlanLevel]  = useState("beginner")
  const [essayStyle, setEssayStyle] = useState("analytical")
  const [essayLen,   setEssayLen]   = useState("medium")
  const [presStyle,  setPresStyle]  = useState("professional")
  const [presSlides, setPresSlides] = useState(10)

  const loadRef    = useRef(null)
  const resultRef  = useRef(null)

  const showToast = (msg, type = "success") => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const startLoad = (m) => {
    setLoadStep(0)
    const steps = LOAD_MSGS[m] || LOAD_MSGS.research
    let i = 0
    loadRef.current = setInterval(() => { i = (i+1) % steps.length; setLoadStep(i) }, 2000)
  }
  const stopLoad = () => { if (loadRef.current) { clearInterval(loadRef.current); loadRef.current = null } }

  const run = async () => {
    const q = (mode === "summarize" ? pasteText : query).trim()
    if (!q || loading) return
    setLoading(true); setResult(null); setQuizData(null); setCardData(null)
    startLoad(mode)

    try {
      let res
      if      (mode === "research")     res = await api("POST","/research",     { query: q })
      else if (mode === "explain")      res = await api("POST","/explain",      { topic: q, level: explainLvl, analogy: true })
      else if (mode === "quiz")         res = await api("POST","/quiz",         { topic: q, num: quizNum, difficulty: quizDiff, style: quizStyle })
      else if (mode === "flashcards")   res = await api("POST","/flashcards",   { topic: q, num: cardNum })
      else if (mode === "summarize")    res = await api("POST","/summarize",    { text: q, style: sumStyle, length: sumLen })
      else if (mode === "study-plan")   res = await api("POST","/study-plan",   { subject: q, exam_date: planDate, hours_per_day: planHours, current_level: planLevel })
      else if (mode === "essay")        res = await api("POST","/essay",        { topic: q, style: essayStyle, length: essayLen })
      else if (mode === "presentation") res = await api("POST","/presentation",  { topic: q, slides: presSlides, style: presStyle })

      if (mode === "quiz") {
        setQuizData(res)
      } else if (mode === "flashcards") {
        setCardData(res)
      } else {
        const content = res?.content || res?.result || res?.essay || res?.presentation || res?.outline || JSON.stringify(res)
        const entry = { id: Date.now(), mode, query: q, content, ts: new Date().toLocaleTimeString([], { hour:"2-digit", minute:"2-digit" }) }
        setResult(entry)
        setHistory(p => [entry, ...p.slice(0,9)])
      }
      showToast({ research:"Research complete", explain:"Explanation ready", quiz:"Quiz generated",
        flashcards:"Flashcards ready", summarize:"Summary done", "study-plan":"Plan created",
        essay:"Essay written", presentation:"Slides ready" }[mode] || "Done")
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior:"smooth", block:"start" }), 100)
    } catch (e) {
      showToast(e.name === "AbortError" ? "Timed out (90s)" : e.message || "Failed", "error")
    } finally {
      setLoading(false); stopLoad()
    }
  }

  const copy   = (text) => { navigator.clipboard.writeText(text); showToast("Copied") }
  const save   = (text, label) => {
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([text], { type:"text/plain" })),
      download: `ORA-${label}-${Date.now()}.txt`,
    }); a.click()
  }

  const curMode = MODES.find(m => m.id === mode)
  const loadSteps = LOAD_MSGS[mode] || LOAD_MSGS.research
  const suggestions = SUGGESTIONS[mode] || []

  return (
    <div className="page" style={{ maxWidth:820, margin:"0 auto" }}>

      {/* ── Header ── */}
      <div className="page-header">
        <div>
          <div className="page-title">📚 STUDY LAB</div>
          <div className="page-subtitle">YOUR PERSONAL STUDY PARTNER</div>
        </div>
        <div style={{ display:"flex", gap:8 }}>
          {history.length > 0 && (
            <button className="btn btn-sm" onClick={() => setShowHist(v=>!v)}>
              🕐 {history.length}
            </button>
          )}
        </div>
      </div>

      {/* ── Mode grid ── */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(88px,1fr))", gap:8, marginBottom:16 }}>
        {MODES.map(m => (
          <button key={m.id} onClick={() => { setMode(m.id); setResult(null); setQuizData(null); setCardData(null) }} disabled={loading}
            style={{
              display:"flex", flexDirection:"column", alignItems:"center", gap:4,
              padding:"10px 6px", background: mode===m.id ? "rgba(0,255,157,0.08)" : "var(--bg-card)",
              border:`1px solid ${mode===m.id ? "var(--green)" : "var(--border)"}`,
              borderRadius:"var(--radius-lg)", cursor:"pointer", transition:"all 0.15s",
            }}>
            <span style={{ fontSize:18, color: mode===m.id ? "var(--green)" : "var(--text-3)" }}>{m.icon}</span>
            <span style={{ fontFamily:"var(--mono)", fontSize:8, fontWeight:700, letterSpacing:1,
              color: mode===m.id ? "var(--green)" : "var(--text-4)" }}>{m.label.toUpperCase()}</span>
          </button>
        ))}
      </div>

      {/* ── History ── */}
      {showHist && history.length > 0 && (
        <div className="card" style={{ marginBottom:14 }}>
          <div className="card-header">
            <span className="card-title">HISTORY</span>
            <button className="btn btn-sm" onClick={() => setShowHist(false)}>✕</button>
          </div>
          <div style={{ maxHeight:220, overflowY:"auto" }}>
            {history.map(item => (
              <div key={item.id} onClick={() => { setResult(item); setShowHist(false); setTimeout(()=>resultRef.current?.scrollIntoView({behavior:"smooth"}),100) }}
                style={{ padding:"10px 16px", borderBottom:"1px solid var(--border)", cursor:"pointer",
                  display:"flex", alignItems:"center", gap:10 }}
                onMouseEnter={e=>e.currentTarget.style.background="var(--bg-2)"}
                onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                <span>{MODES.find(m=>m.id===item.mode)?.icon||"⊕"}</span>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:12, color:"var(--text-1)", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{item.query}</div>
                  <div className="mono text-xs" style={{ color:"var(--text-4)" }}>{item.mode.toUpperCase()} · {item.ts}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Input card ── */}
      <div className="card" style={{ border: loading ? "1px solid rgba(0,255,157,0.3)" : undefined }}>
        <div className="card-header">
          <span className="card-title">{curMode?.icon} {curMode?.label?.toUpperCase()}</span>
          <span style={{ fontSize:10, color:"var(--text-5)" }}>{curMode?.desc}</span>
        </div>
        <div className="card-body" style={{ display:"flex", flexDirection:"column", gap:12 }}>

          {/* Summarize: paste area */}
          {mode === "summarize" ? (
            <textarea className="textarea" value={pasteText} onChange={e=>setPasteText(e.target.value)}
              placeholder="Paste the text you want to summarize here..." disabled={loading}
              style={{ minHeight:120, fontSize:13, resize:"vertical" }} />
          ) : (
            <textarea className="textarea" value={query} onChange={e=>setQuery(e.target.value)}
              onKeyDown={e=>{ if(e.key==="Enter"&&!e.shiftKey&&window.innerWidth>=768){e.preventDefault();run()} }}
              disabled={loading}
              placeholder={
                mode==="research"     ? "What do you want to research?" :
                mode==="explain"      ? "What concept do you want explained?" :
                mode==="quiz"         ? "What topic should the quiz cover?" :
                mode==="flashcards"   ? "What topic should the flashcards cover?" :
                mode==="study-plan"   ? "What subject are you studying?" :
                mode==="essay"        ? "What should the essay be about?" :
                                        "What should the presentation cover?"
              }
              style={{ minHeight:72, resize:"none", fontSize:14, lineHeight:1.6 }} />
          )}

          {/* Suggestions */}
          {!query && !pasteText && suggestions.length > 0 && !loading && (
            <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
              {suggestions.map(s => (
                <button key={s} onClick={() => setQuery(s)} style={{
                  background:"var(--bg-2)", border:"1px solid var(--border-2)", borderRadius:16,
                  color:"var(--text-3)", fontSize:11, padding:"4px 10px", cursor:"pointer", fontFamily:"var(--sans)",
                  transition:"all 0.15s",
                }}
                  onMouseEnter={e=>{e.currentTarget.style.borderColor="var(--text-4)";e.currentTarget.style.color="var(--text-2)"}}
                  onMouseLeave={e=>{e.currentTarget.style.borderColor="var(--border-2)";e.currentTarget.style.color="var(--text-3)"}}
                >{s}</button>
              ))}
            </div>
          )}

          {/* Mode-specific options */}
          {mode === "quiz" && (
            <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
              {[
                { label:"QUESTIONS", el: <select className="select" value={quizNum} onChange={e=>setQuizNum(+e.target.value)} style={{width:"100%"}}>
                    {[3,5,8,10,15].map(n=><option key={n} value={n}>{n} questions</option>)}</select> },
                { label:"DIFFICULTY", el: <select className="select" value={quizDiff} onChange={e=>setQuizDiff(e.target.value)} style={{width:"100%"}}>
                    <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select> },
                { label:"STYLE", el: <select className="select" value={quizStyle} onChange={e=>setQuizStyle(e.target.value)} style={{width:"100%"}}>
                    <option value="mcq">Multiple Choice</option><option value="true_false">True / False</option>
                    <option value="short_answer">Short Answer</option><option value="mixed">Mixed</option></select> },
              ].map(({label,el}) => (
                <div key={label} style={{ flex:"1 1 120px" }}>
                  <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:4 }}>{label}</div>
                  {el}
                </div>
              ))}
            </div>
          )}

          {mode === "flashcards" && (
            <div>
              <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:4 }}>NUMBER OF CARDS</div>
              <select className="select" value={cardNum} onChange={e=>setCardNum(+e.target.value)}>
                {[5,10,15,20].map(n=><option key={n} value={n}>{n} cards</option>)}
              </select>
            </div>
          )}

          {mode === "explain" && (
            <div>
              <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:4 }}>KNOWLEDGE LEVEL</div>
              <div style={{ display:"flex", gap:6 }}>
                {["beginner","intermediate","advanced"].map(l => (
                  <button key={l} onClick={() => setExplainLvl(l)}
                    style={{ flex:1, padding:"7px 4px", fontFamily:"var(--mono)", fontSize:9, letterSpacing:1, fontWeight:700,
                      background: explainLvl===l ? "rgba(0,255,157,0.1)" : "var(--bg-2)",
                      border:`1px solid ${explainLvl===l ? "var(--green)" : "var(--border)"}`,
                      color: explainLvl===l ? "var(--green)" : "var(--text-4)",
                      borderRadius:"var(--radius)", cursor:"pointer" }}>
                    {l.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mode === "summarize" && (
            <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
              {[
                { label:"FORMAT", val:sumStyle, set:setSumStyle, opts:[["bullet","Bullet Points"],["paragraph","Paragraphs"],["cornell","Cornell Notes"],["mindmap","Mind Map"]] },
                { label:"LENGTH", val:sumLen,   set:setSumLen,   opts:[["short","Short"],["medium","Medium"],["detailed","Detailed"]] },
              ].map(({label,val,set,opts}) => (
                <div key={label} style={{ flex:"1 1 140px" }}>
                  <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:4 }}>{label}</div>
                  <select className="select" value={val} onChange={e=>set(e.target.value)} style={{ width:"100%" }}>
                    {opts.map(([v,l])=><option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              ))}
            </div>
          )}

          {mode === "study-plan" && (
            <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
              {[
                { label:"EXAM IN",        el:<input className="input" value={planDate}  onChange={e=>setPlanDate(e.target.value)}  placeholder="e.g. 2 weeks, 30 days" style={{fontSize:12}} /> },
                { label:"HOURS/DAY",      el:<input className="input" type="number" min={0.5} max={12} step={0.5} value={planHours} onChange={e=>setPlanHours(+e.target.value)} style={{fontSize:12}} /> },
                { label:"CURRENT LEVEL",  el:<select className="select" value={planLevel} onChange={e=>setPlanLevel(e.target.value)} style={{width:"100%"}}>
                    <option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select> },
              ].map(({label,el}) => (
                <div key={label} style={{ flex:"1 1 140px" }}>
                  <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:4 }}>{label}</div>
                  {el}
                </div>
              ))}
            </div>
          )}

          {mode === "essay" && (
            <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
              {[
                { label:"STYLE",  val:essayStyle, set:setEssayStyle, opts:[["analytical","Analytical"],["narrative","Narrative"],["persuasive","Persuasive"],["expository","Expository"]] },
                { label:"LENGTH", val:essayLen,   set:setEssayLen,   opts:[["short","Short (~500w)"],["medium","Medium (~1000w)"],["long","Long (~2000w)"]] },
              ].map(({label,val,set,opts}) => (
                <div key={label} style={{ flex:"1 1 140px" }}>
                  <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:4 }}>{label}</div>
                  <select className="select" value={val} onChange={e=>set(e.target.value)} style={{width:"100%"}}>
                    {opts.map(([v,l])=><option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              ))}
            </div>
          )}

          {mode === "presentation" && (
            <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
              {[
                { label:"STYLE",  val:presStyle,  set:setPresStyle,  opts:[["professional","Professional"],["academic","Academic"],["pitch","Pitch Deck"],["tutorial","Tutorial"]] },
                { label:"SLIDES", val:presSlides, set:setPresSlides, opts:[[5,"5 slides"],[8,"8 slides"],[10,"10 slides"],[15,"15 slides"],[20,"20 slides"]] },
              ].map(({label,val,set,opts}) => (
                <div key={label} style={{ flex:"1 1 140px" }}>
                  <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:4 }}>{label}</div>
                  <select className="select" value={val} onChange={e=>set(typeof opts[0][0]==="number" ? +e.target.value : e.target.value)} style={{width:"100%"}}>
                    {opts.map(([v,l])=><option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              ))}
            </div>
          )}

          {/* Run button */}
          <button className="btn btn-green" onClick={run}
            disabled={loading || !(mode==="summarize" ? pasteText.trim() : query.trim())}
            style={{ width:"100%", justifyContent:"center", padding:12, fontSize:12, letterSpacing:2 }}>
            {loading
              ? <><div className="spinner" style={{width:14,height:14,borderWidth:2}} /> {loadSteps[loadStep]}</>
              : `${curMode?.icon} ${curMode?.label?.toUpperCase()}`}
          </button>
        </div>
      </div>

      {/* ── Loading bar ── */}
      {loading && (
        <div style={{ background:"rgba(0,255,157,0.04)", border:"1px solid rgba(0,255,157,0.15)",
          borderRadius:"var(--radius-lg)", padding:"14px 18px", marginBottom:14,
          display:"flex", alignItems:"center", gap:14 }}>
          <div style={{ position:"relative", width:32, height:32, flexShrink:0 }}>
            <div className="spinner" style={{ width:32, height:32, borderWidth:3, position:"absolute" }} />
            <span style={{ position:"absolute", inset:0, display:"flex", alignItems:"center",
              justifyContent:"center", fontSize:13 }}>{curMode?.icon}</span>
          </div>
          <div style={{ flex:1 }}>
            <div className="mono" style={{ fontSize:10, color:"var(--green)", letterSpacing:2, marginBottom:6 }}>
              {loadSteps[loadStep].toUpperCase()}
            </div>
            <div style={{ display:"flex", gap:4 }}>
              {loadSteps.map((_,i) => (
                <div key={i} style={{ width:6, height:6, borderRadius:"50%",
                  background: i<=loadStep ? "var(--green)" : "var(--border-2)", transition:"background 0.3s" }} />
              ))}
            </div>
          </div>
          <div className="mono" style={{ fontSize:10, color:"var(--text-5)" }}>90s MAX</div>
        </div>
      )}

      {/* ── Quiz result ── */}
      {quizData && !loading && (
        <div className="card" ref={resultRef} style={{ border:"1px solid rgba(0,255,157,0.2)" }}>
          <div className="card-header">
            <span className="card-title">◆ QUIZ · {quizData.topic}</span>
            <span className="card-badge">{quizData.questions?.length || 0} QUESTIONS · {quizData.difficulty?.toUpperCase()}</span>
          </div>
          <div className="card-body">
            <QuizRunner data={quizData} onRetry={() => { setQuizData(null); run() }} />
          </div>
        </div>
      )}

      {/* ── Flashcard result ── */}
      {cardData && !loading && (
        <div className="card" ref={resultRef} style={{ border:"1px solid rgba(0,255,157,0.2)" }}>
          <div className="card-header">
            <span className="card-title">▣ FLASHCARDS · {cardData.topic}</span>
            <span className="card-badge">{cardData.cards?.length || 0} CARDS</span>
          </div>
          <div className="card-body">
            <FlashcardDeck data={cardData} onRetry={() => { setCardData(null); run() }} />
          </div>
        </div>
      )}

      {/* ── Text result ── */}
      {result && !loading && !quizData && !cardData && (
        <div className="card" ref={resultRef} style={{ border:"1px solid rgba(0,255,157,0.2)" }}>
          <div className="card-header">
            <span className="card-title">{curMode?.icon} {result.mode.toUpperCase()} RESULT</span>
            <div style={{ display:"flex", gap:6 }}>
              <button className="btn btn-sm" onClick={() => copy(result.content)}>⎘ COPY</button>
              <button className="btn btn-sm" onClick={() => save(result.content, result.mode)}>↓ SAVE</button>
              <button className="btn btn-sm btn-red" onClick={() => setResult(null)}>✕</button>
            </div>
          </div>
          <div className="card-body">
            <div className="mono text-xs" style={{ color:"var(--text-4)", marginBottom:12,
              borderLeft:"2px solid var(--green)", paddingLeft:8 }}>{result.query}</div>
            <Md text={result.content} />
            <div style={{ marginTop:14, paddingTop:12, borderTop:"1px solid var(--border)", display:"flex", gap:8, flexWrap:"wrap" }}>
              <button className="btn btn-sm" onClick={() => { mode==="summarize" ? setPasteText(result.query) : setQuery(result.query); setResult(null) }}>↺ REFINE</button>
              {result.mode === "research" && <button className="btn btn-sm" onClick={() => { setQuery(result.query); setMode("quiz"); setResult(null) }}>◆ MAKE QUIZ</button>}
              {result.mode === "research" && <button className="btn btn-sm" onClick={() => { setQuery(result.query); setMode("flashcards"); setResult(null) }}>▣ FLASHCARDS</button>}
              {result.mode === "research" && <button className="btn btn-sm" onClick={() => { setQuery(result.query); setMode("essay"); setResult(null) }}>✎ ESSAY</button>}
              {result.mode === "explain"  && <button className="btn btn-sm" onClick={() => { setQuery(result.query); setMode("quiz"); setResult(null) }}>◆ TEST ME</button>}
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`toast ${toast.type==="error"?"error":"success"}`}>
          {toast.type==="error" ? "⚠" : "✓"} {toast.msg}
        </div>
      )}
    </div>
  )
}

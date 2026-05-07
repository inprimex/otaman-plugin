# AI / ML — Estimation Reference

## What's distinctive about this domain

AI/ML estimation is dominated by uncertainty that doesn't exist in conventional software: model behavior is non-deterministic, evaluation is harder than implementation, and inference cost can dominate operating expense in ways that flip business model assumptions. The most common pre-sales failure is treating AI features as deterministic: scoping a "chatbot" the same way you'd scope a CRUD form, then discovering that prompt engineering, eval infrastructure, hallucination handling, cost-per-request modeling, and human-in-the-loop fallbacks together cost 3–5× the original feature estimate. Discovery for AI projects must include eval methodology and cost modeling — not just functional requirements.

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| EU AI Act (high-risk) | Healthcare, credit scoring, employment, education, critical infrastructure | +20–40%; conformity assessment, documentation, post-market monitoring |
| EU AI Act (limited risk) | Chatbots, deepfakes, content generation | +5–10%; transparency obligations |
| EU AI Act (minimal risk) | Most other applications | minimal |
| GDPR + automated decision-making (Art. 22) | EU users, decisions with legal/significant effects | +10–20%; right to human review, explanations |
| HIPAA | Healthcare AI (clinical decision, patient-facing) | see healthcare.md; AI adds complexity to PHI handling |
| SR 11-7 (US Fed) | Models used in regulated banking decisions | +25–50%; model risk management, validation, monitoring |
| FDA SaMD (Software as Medical Device) | AI used clinically | see healthcare.md FDA notes; AI/ML adds Predetermined Change Control Plan complexity |
| Copyright (training data) | Generative AI using third-party content | varies; growing legal uncertainty (NYT v. OpenAI etc.) |
| Privacy of training data | AI trained on user-provided data | +10–15%; consent, opt-out, data minimization |
| ISO 42001 | Voluntary AI management system standard | +10–15% if pursuing certification |

The EU AI Act is the regulatory development with biggest near-term cost impact. Most fintech, healthcare, employment, and education AI applications land in the high-risk category. Treat it as a hard scoping question in Discovery.

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| LLM API (frontier) | Anthropic Claude, OpenAI, Google Gemini, AWS Bedrock | 30–80h foundation | Standard prompt+response is straightforward; streaming, tool use, structured outputs add complexity |
| LLM self-hosted | vLLM, SGLang, Ollama, llama.cpp | 80–250h infrastructure | GPU procurement and ops is its own challenge; only worth it at scale or for compliance reasons |
| Vector database | Pinecone, Weaviate, Qdrant, pgvector, Chroma, Turbopuffer | 40–120h | pgvector is fine for <10M vectors; managed services for scale |
| Embeddings | Voyage AI, OpenAI ada/3-large, Cohere, BGE (open) | 20–40h | Choice affects retrieval quality more than people expect; benchmark before committing |
| RAG framework | LangChain, LlamaIndex, Haystack, custom | 60–200h | Off-the-shelf is fast for prototype; production rarely runs on default settings |
| Agent framework | LangGraph, CrewAI, Letta, custom | 100–400h | Agentic systems are research territory in production; budget generously for iteration |
| Eval infrastructure | Braintrust, LangSmith, Helicone, custom | 60–200h | Underestimated category; you can't improve what you can't measure |
| Prompt management | PromptLayer, Langfuse, custom | 40–120h | Versioning, A/B testing, rollback |
| Document processing | Unstructured.io, LlamaParse, Reducto, AWS Textract | 40–150h | Quality varies dramatically by document type |
| Voice / speech | OpenAI Whisper, AssemblyAI, Deepgram, ElevenLabs (synthesis) | 40–120h | Real-time streaming is significantly more complex than batch |
| Vision / OCR | OpenAI vision, Anthropic vision, Google Document AI, Tesseract | 40–150h | LLM vision is good for understanding; specialized OCR is better for extraction |
| Fine-tuning | OpenAI, Anthropic (limited), self-host with HuggingFace | 80–400h | RAG often outperforms fine-tuning at lower cost; consider before committing |
| Model monitoring | Arize, WhyLabs, Evidently AI, custom | 60–180h | Drift detection, performance regression, cost monitoring |
| ML training infrastructure | Modal, RunPod, Lambda Labs, AWS SageMaker, GCP Vertex | 80–250h foundation | Most products don't train models; if you do, this is meaningful work |

## Feature taxonomy (typical modules)

- **Conversational Interface** — chat UI, message history, streaming responses, citations
- **Knowledge Retrieval (RAG)** — document ingestion, chunking, embedding, retrieval, re-ranking
- **Agent / Tool Use** — tool definition, planning, execution, error handling
- **Document Understanding** — extraction, classification, summarization, Q&A over documents
- **Generation** — text, image, audio, video generation with controls
- **Personalization** — user-specific context, memory, preference learning
- **Eval & Quality** — golden datasets, automated evals, regression detection, human review
- **Cost Management** — per-request cost tracking, budgets, model routing (cheaper-first), caching
- **Safety & Trust** — content filtering, jailbreak detection, output validation, human-in-the-loop escalation
- **Admin / Observability** — prompt versioning, model selection, A/B tests, usage analytics
- **Data Pipelines** — ingestion, preprocessing, embedding refresh, training data curation

## Recommended features sheet schema

For LLM-application projects (most current AI work):
- Backend (hours)
- Frontend (hours)
- LLM/RAG Pipeline (hours)
- Eval Infrastructure (hours)
- **Total (hours)**

For ML platform / training-included projects:
- Backend (hours)
- Frontend (hours)
- ML Engineering (hours) — model training, fine-tuning, deployment
- Data Pipeline (hours)
- Eval Infrastructure (hours)
- **Total (hours)**

Eval infrastructure deserves its own column because it's chronically under-scoped. Without dedicated eval work, AI products ship and degrade silently.

## Domain-specific risk register additions

### Risk: Hallucinations cause user harm or legal exposure

- **Category**: Technical / Legal
- **Probability / Impact**: High / High
- **Description**: LLMs produce confident-seeming wrong answers. Severity ranges from minor user frustration to legal liability (medical, financial, legal advice).
- **Mitigation**: Retrieval-augmented architecture grounding answers in verified sources; citations to sources in every response; explicit "I don't know" pathways; output validation against schemas; human-in-the-loop for high-stakes decisions; clear UI signaling of AI-generated content.
- **Contingency**: Disable AI feature for affected use case; manual escalation pathway; if user-facing harm, incident response and notification per terms of service.

### Risk: Inference costs exceed business model assumptions

- **Category**: Commercial
- **Probability / Impact**: Medium / High
- **Description**: AI features can cost $0.01–$2.00+ per user interaction depending on model, context length, and request frequency. Free-tier users at scale or chatty users on flat-rate plans can break unit economics.
- **Mitigation**: Cost modeling during Discovery (per request × expected volume × growth); model routing (cheap-first, escalate to expensive on need); aggressive caching of similar requests; prompt optimization for token efficiency; usage limits per user tier.
- **Contingency**: Switch to cheaper model with quality trade-off documented; introduce usage limits or paid tier sooner than planned; renegotiate provider commits.

### Risk: Eval infrastructure underbuilt; quality degrades silently

- **Category**: Operational
- **Probability / Impact**: High / Medium
- **Description**: Without proactive eval, model upgrades, prompt changes, or context shifts can degrade output quality without anyone noticing. Users notice eventually, but trust damage is hard to reverse.
- **Mitigation**: Eval infrastructure (golden datasets, automated scoring) built in MVP, not added later; regression checks on every prompt or model change; user feedback signal collection (thumbs up/down at minimum).
- **Contingency**: Roll back to previous prompt/model version; manual review of recent outputs; user communication if material drop.

### Risk: Vendor model deprecation or pricing changes

- **Category**: Commercial / Technical
- **Probability / Impact**: Medium / Medium
- **Description**: Foundation model vendors deprecate models, change pricing, or change behavior. Products built tightly to one model can be disrupted on vendor's timeline.
- **Mitigation**: Abstraction layer over model calls (LiteLLM, custom router); regular eval against alternate providers; contract with reasonable notice periods.
- **Contingency**: Migration playbook to alternate model documented; eval coverage sufficient to validate alternate; communicate with affected users if quality changes.

### Risk: Training data ingest creates copyright or privacy liability

- **Category**: Legal
- **Probability / Impact**: Low / Critical
- **Description**: Fine-tuning or training on customer data, scraped web data, or third-party content creates legal exposure. Recent litigation makes this a moving target.
- **Mitigation**: Counsel review of all training data sources; explicit licensing or consent for any non-public data; preference for RAG over fine-tuning where it suffices; data lineage tracking.
- **Contingency**: Model retrain without affected data; legal response per counsel; user notification per privacy policy.

## AI-assisted productivity profile (overrides for AI/ML)

- **LLM API integration code** — substantial speedup (40%+); patterns are exactly what AI training has seen most
- **RAG pipeline boilerplate** — meaningful speedup (30%+); retrieval, chunking, embedding patterns are common
- **Prompt engineering** — variable; AI can suggest but humans decide; productivity gain is in iteration speed, not initial drafting
- **Eval logic and golden datasets** — modest speedup (15–25%); domain-specific quality criteria require human judgment
- **ML training code** — limited speedup (15–20%); training behavior is empirical; AI suggestions need validation
- **Model selection and architecture decisions** — minimal AI gain; this is research and judgment, not code generation

## Anchor projects (typical scale calibration)

### Anchor: Internal RAG knowledge assistant, 3-month delivery

- **Scope**: Slack/web chat interface over company documents (Notion, Confluence, Drive), with citations and feedback loop
- **Total feature hours**: ~700h
- **Total cost** (at $70/h blended): ~$80K
- **Timeline**: 3-week discovery + 2.5-month development
- **Notable cost drivers**: Document ingestion pipeline, eval framework, source connector engineering

### Anchor: Customer-facing AI feature in existing SaaS product, 4-month delivery

- **Scope**: AI assistant integrated into existing product, contextual to user data, full eval and cost monitoring
- **Total feature hours**: ~1,200h
- **Total cost**: ~$140K–$170K
- **Timeline**: 4-week discovery (incl. cost modeling) + 3-month development
- **Notable cost drivers**: Integration with existing data model, eval infrastructure, cost management UI, safety/trust features

### Anchor: Production agentic system (multi-step tool use), 6-month delivery

- **Scope**: AI agent that takes actions on user behalf via multiple integrations, with reliability and safety controls
- **Total feature hours**: ~2,500h
- **Total cost**: ~$300K–$400K
- **Timeline**: 6-week discovery + 5-month development
- **Notable cost drivers**: Agent reliability engineering (this is the hard part), tool integrations, eval at agent level not just LLM level, observability

### Anchor: Custom ML model platform (training included), 9-month delivery

- **Scope**: End-to-end ML platform with training pipeline, model registry, deployment, monitoring; for a specific domain problem
- **Total feature hours**: ~3,500h
- **Total cost**: ~$450K–$600K
- **Timeline**: 8-week discovery + 7-month development
- **Notable cost drivers**: Data pipeline, training infrastructure, MLOps tooling, evaluation harness, model serving infrastructure

## Common pitfalls in pre-sales for AI/ML

- "We want a ChatGPT for X" — clarify whether they need conversational interface, RAG, agentic action-taking, or domain-tuned model; cost and complexity vary 5–10×
- Eval as afterthought — without eval infrastructure built in MVP, the product ships and quality degrades; budget eval from Day 1
- Cost modeling skipped in pre-sales — at scale, inference cost can be 30–60% of all operating cost; needs to be modeled before quoting
- Conflating fine-tuning with RAG — fine-tuning is rarely the right answer in 2026; RAG is faster, cheaper, and more correct for most use cases
- "Build our own model" — clients regularly request training a custom foundation model; almost always the wrong call vs. using frontier model with RAG
- Underestimating non-determinism's impact on testing — traditional QA approaches don't work for AI; eval-based QA is the alternative
- Underestimating prompt engineering — prompts are software; they need versioning, testing, deployment processes; not a side activity
- Hallucination handling skipped — every AI product needs explicit handling of "model is wrong" pathways; rarely scoped initially

## Domain-specific Gate 0 checks

- [ ] Identify whether use case is generation, retrieval, classification, agentic, or hybrid
- [ ] Confirm whether human-in-the-loop is required (regulatory, safety, quality)
- [ ] Identify model preference (frontier API, open-source self-hosted, both)
- [ ] Confirm whether training/fine-tuning is in scope (usually shouldn't be in MVP)
- [ ] Identify expected per-user interaction frequency (drives cost modeling)
- [ ] Confirm acceptable latency (real-time chat vs. batch document processing)
- [ ] Identify EU AI Act risk category (especially if any EU users)
- [ ] Confirm data sensitivity (drives self-hosted vs. API decision)
- [ ] Identify eval methodology — how will quality be measured?
- [ ] Confirm cost ceiling per user / per request

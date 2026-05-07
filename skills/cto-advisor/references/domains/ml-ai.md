# AI / ML — Strategic Advisory Reference

## What's distinctive about advising in this domain

AI/ML CTO conversations in 2026 are dominated by an asymmetry: capability moves faster than organizational ability to absorb it. The strategic question is rarely "can we use AI" but "what should we resist using AI for, and how do we build durable advantage when the underlying models are commoditizing." Push back on the assumption that AI is a feature to add — for most products, it's a redesign of the product itself, with implications for unit economics, eval infrastructure, hallucination handling, vendor risk, and cost management that cut across every functional area.

## Vendor landscape

### Foundation model providers

- **Anthropic Claude**: Strong for reasoning, coding, long-context, agentic tool use. Claude Opus / Sonnet / Haiku tiers. Default for many production applications in 2026.
- **OpenAI**: Broadest model family (GPT, o-series, etc.); often default for prototyping. Mature API; aggressive pricing pressure.
- **Google Gemini**: Strong multimodal capability, very long context, native Google services integration.
- **Open-source / self-hosted**: Llama, Mistral, Qwen, DeepSeek — viable for cost or compliance reasons, lag frontier on quality
- **AWS Bedrock**: Multi-provider abstraction; convenient if AWS-anchored
- **Azure OpenAI**: For enterprises requiring Microsoft contractual posture

### Vector / retrieval infrastructure

- **pgvector**: Default for <10M vectors; PostgreSQL extension; minimal operational overhead
- **Pinecone**: Managed; mature; expensive at scale
- **Qdrant**: Open-source + managed; growing adoption
- **Weaviate**: Open-source + managed; rich filtering
- **Turbopuffer**: Newer; cost-efficient for read-heavy workloads
- **Chroma**: Lightweight; popular for prototyping

### LLM application frameworks

- **LangChain / LangGraph**: Most popular; criticized for over-abstraction; LangGraph is the agent framework path
- **LlamaIndex**: RAG-focused
- **Haystack**: Open-source; mature
- **Vercel AI SDK**: Lightweight; popular for Next.js apps
- **Mastra**: Newer agentic framework
- **Custom**: Often the right answer past initial prototyping

### Eval & observability

- **Braintrust**: Strong eval infrastructure; popular in 2026
- **LangSmith**: Tied to LangChain ecosystem
- **Helicone**: Cost monitoring focus
- **Weights & Biases**: ML training and eval
- **Arize, WhyLabs, Evidently**: Model monitoring at production

### Embedding providers

- **Voyage AI**: Strong quality, often best for code or domain-specific
- **OpenAI text-embedding-3**: Solid default
- **Cohere**: Good multilingual
- **Open-source (BGE, E5)**: Self-hostable; competitive quality

### Inference infrastructure (self-hosted)

- **vLLM / SGLang**: Production-grade open-source serving
- **Together AI / Fireworks / Anyscale**: Managed inference for open models
- **Modal, Replicate, Baseten**: Serverless inference

## Hiring patterns

- **First hire profile**: Senior engineer with strong product sense and AI fluency, not necessarily ML research background. The work is more LLM application engineering than ML research for most products. Familiarity with eval-driven development is critical.
- **Common gaps**:
  - **AI/ML engineer specialized in evals** — without dedicated eval focus, quality degrades silently
  - **Prompt engineer** — emerging discipline; often combines product, engineering, and content sensibilities
  - **AI product designer** — designing for non-deterministic outputs, error handling, trust signals is its own discipline
- **Specialist roles**: Eval engineer, AI safety / red team (for high-risk applications), data engineer for training data and RAG pipelines
- **Outsourcing patterns**: Foundational research outsourced to model providers (don't train your own model unless you have strong reasons); fine-tuning sometimes outsourced; eval and prompt engineering should be in-house once the product matters.

## Common architectural debates

### "Use frontier model API vs. self-host open model"

Default position: use frontier API. Frontier quality is meaningfully better; ops complexity of self-hosting is significant; per-token economics favor APIs unless very high volume.

Flip when: regulatory or compliance reasons require data not leaving infrastructure; volume is high enough that economics flip (typically very large scale); specific fine-tuning needs that frontier APIs don't support.

### "RAG vs. fine-tuning"

Default position: RAG. Fine-tuning rarely outperforms well-built RAG, costs more, takes longer, requires retraining when knowledge changes.

Flip when: domain language is so specialized that frontier model performs poorly even with retrieval; format/style adaptation matters more than knowledge (rare); regulatory framework requires deterministic behavior.

### "Build agentic vs. structured workflow"

Default position in 2026: structured workflow with LLM nodes for most production applications. Fully agentic systems are still hard to make reliable in production.

Flip when: task structure is genuinely emergent (research, complex problem-solving); user accepts variable behavior; you have eval infrastructure to detect agent failures.

### "Single model vs. model routing"

Default position: start with single best model, optimize for capability over cost. Add routing once volume justifies cost optimization.

Flip when: cost dominates and volume justifies complexity; specific tasks benefit from specialized models (vision, code, reasoning).

### "Build eval infrastructure vs. ship faster"

Default position: build eval infrastructure from MVP. Without it, you can't safely change prompts, models, or context — and you'll need to change all three frequently.

This is the single most common skipped step that hurts AI products in production.

## Regulatory bottlenecks

- **EU AI Act high-risk classification**: 6–12 month conformity assessment for high-risk applications
- **GDPR Art 22 (automated decision-making) DPIA**: 4–8 weeks
- **Sector-specific approvals (healthcare AI, finance models)**: 6–18 months depending on regulator
- **Copyright / training data review**: Highly uncertain; growing legal risk landscape
- **Customer data processing agreements amendments**: 4–12 weeks per major customer when AI features added

## Common pitfalls in advisory for AI/ML

- Treating AI as a feature rather than a product redesign — the business model implications are usually larger than expected
- Skipping eval infrastructure — without it, quality degrades silently on every prompt change
- Underestimating cost at scale — inference costs can dominate operating expense
- Assuming hallucinations can be eliminated — they can't, only managed; design for them
- Recommending fine-tuning when RAG would serve better
- Building agentic systems prematurely — reliability cliff is steep
- Underestimating prompt engineering as a discipline
- Vendor lock-in to one model — abstract model calls behind a router from start
- Using AI to ship faster but not designing for AI's failure modes

## Escalation triggers specific to AI/ML

- High-risk use case classification (healthcare clinical decision, credit, hiring, education) requires legal + ethics review before development
- Training on customer data requires legal + DPO review
- Generative content for end users (especially regulated industries) requires content/safety strategy at executive level
- Vendor model deprecation or pricing changes affecting unit economics require CFO involvement
- AI-generated harm incidents require communications + legal + product simultaneously
- Decisions to build foundation models are CEO/board-level (almost always wrong call for product companies)

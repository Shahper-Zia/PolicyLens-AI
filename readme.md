# PolicyLens-AI

**AI-Powered Payer Policy Intelligence & Access Quality Scoring System**

PolicyLens-AI is an enterprise-grade GenAI pipeline that transforms complex Prior Authorization (PA) policy documents into structured payer access intelligence. The system extracts clinically and commercially relevant access parameters from unstructured payer PDFs and computes an explainable Access Quality Score (0–100) to quantify payer restrictiveness and market access quality.

Instead of treating this as simple PDF extraction, PolicyLens-AI approaches the challenge as a **document intelligence and policy reasoning problem** — combining chunk-level semantic understanding, brand-aware retrieval, logical reasoning, and access scoring.

---

# 📋 Problem Statement

Pharmaceutical manufacturers must analyze hundreds of Prior Authorization (PA) policies across U.S. payers to understand:

* How restrictive payer coverage is
* What barriers exist for patients
* How competitive their market access position is

These payer policies contain:

* Step therapy rules
* Age restrictions
* Specialist requirements
* Quantity limits
* Reauthorization conditions
* TB testing requirements
* Coverage durations
* Multi-brand criteria

The challenge:

* Policies are long, unstructured, inconsistent PDFs
* One PDF may contain multiple brands
* Relevant criteria may appear in non-contiguous sections
* Universal criteria may apply across all brands
* Logic may contain AND/OR conditional reasoning

Manual interpretation is:

* expensive
* slow
* error-prone
* difficult to scale

---

# 🎯 Objective

Build an AI-powered policy intelligence system that:

✅ Reads payer policy PDFs
✅ Understands payer logic and restrictions
✅ Extracts structured access parameters
✅ Handles multi-brand and shared policy sections
✅ Resolves AND/OR logical conditions
✅ Computes explainable Access Quality Scores
✅ Produces benchmark-ready structured outputs

---

# 🧠 Core Innovation

Most extraction systems assume:

```text
One PDF → One Brand → One Continuous Section
```

Real payer policies do not work this way.

PolicyLens-AI introduces a:

# → Chunk Intelligence Architecture

Where:

* documents are split into semantic chunks
* chunks are mapped to brands
* universal criteria are shared across brands
* extraction happens at chunk level
* attribute retrieval is parameter-specific

This architecture improves:

* extraction accuracy
* scalability
* explainability
* robustness against messy payer documents

---

# 🏗️ System Architecture

```text
                          ┌────────────────────┐
                          │  Payer Policy PDFs │
                          └─────────┬──────────┘
                                    │
                                    ▼
                    ┌──────────────────────────┐
                    │ PDF → Markdown Extraction │
                    └─────────┬────────────────┘
                              │
                              ▼
                  ┌─────────────────────────────┐
                  │ Semantic Chunking Engine    │
                  │ - headings                  │
                  │ - tables                    │
                  │ - bullet groups             │
                  │ - paragraphs                │
                  └─────────┬───────────────────┘
                            │
                            ▼
               ┌──────────────────────────────┐
               │ Chunk Classification Layer   │
               │                              │
               │ • Brand Detection            │
               │ • Universal Criteria         │
               │ • Section Type Classification│
               └─────────┬────────────────────┘
                         │
                         ▼
             ┌─────────────────────────────────┐
             │ Brand-wise Chunk Aggregation    │
             │                                 │
             │ TREMFYA → relevant chunks       │
             │ STELARA → relevant chunks       │
             └─────────┬───────────────────────┘
                       │
                       ▼
           ┌──────────────────────────────────┐
           │ Parameter-Specific Retrieval     │
           │                                  │
           │ Age Extractor                    │
           │ Step Therapy Extractor           │
           │ Reauth Extractor                 │
           └─────────┬────────────────────────┘
                     │
                     ▼
          ┌───────────────────────────────────┐
          │ Hybrid Extraction Engine          │
          │                                   │
          │ • Regex / Rules                   │
          │ • Gemini 2.5 Flash                │
          │ • Logical Reasoning               │
          └─────────┬─────────────────────────┘
                    │
                    ▼
         ┌────────────────────────────────────┐
         │ Access Quality Scoring Engine      │
         │                                    │
         │ • Restrictiveness Scoring          │
         │ • Explainability Layer             │
         └─────────┬──────────────────────────┘
                   │
                   ▼
         ┌────────────────────────────────────┐
         │ Final Outputs                      │
         │                                    │
         │ • result.csv                       │
         │ • Dashboard                        │
         │ • Evaluation Metrics               │
         └────────────────────────────────────┘
```

---

# 🧩 Key Design Principles

## 1. Chunk-Level Intelligence

Instead of processing entire PDFs:

* documents are split into semantic chunks
* chunks are independently classified and retrieved

This improves:

* LLM accuracy
* token efficiency
* debugging
* explainability

---

## 2. Multi-Brand Awareness

A single PDF may contain:

* TREMFYA
* STELARA
* shared universal policies

PolicyLens-AI maps:

* brand-specific chunks
* shared universal chunks
* multi-brand chunks

without contaminating extraction results.

---

## 3. Universal Criteria Handling

Example:

* TB testing
* age restrictions
* specialist requirements

may apply to all brands.

The system stores these separately and intelligently associates them with relevant brands.

---

## 4. Retrieval-Augmented Extraction

Instead of sending entire documents to the LLM:

* only parameter-relevant chunks are retrieved

Example:

* Age extractor only sees age-related chunks
* Step therapy extractor only sees therapy-related chunks

This dramatically improves extraction quality.

---

# 📊 Parameters Extracted

The system extracts 12+ clinically and commercially relevant parameters including:

| Category                | Parameters                   |
| ----------------------- | ---------------------------- |
| Eligibility             | Age restrictions             |
| Therapy Logic           | Branded/generic step therapy |
| Diagnostics             | TB test requirements         |
| Prescriber Restrictions | Specialist requirements      |
| Coverage Duration       | Initial authorization        |
| Renewal Rules           | Reauthorization duration     |
| Utilization Management  | Quantity limits              |
| Access Intelligence     | Access Quality Score         |

---

# 📈 Access Quality Score (0–100)

PolicyLens-AI computes an explainable access score.

| Score | Meaning              |
| ----- | -------------------- |
| 0     | No access            |
| 25    | Highly restrictive   |
| 50    | FDA parity           |
| 75    | Preferred access     |
| 100   | Best possible access |

---

# 🧮 Example Scoring Logic

```python
score = 50

score -= branded_steps * 10
score -= generic_steps * 5

if tb_test_required:
    score -= 5

if phototherapy_required:
    score -= 10

if auth_duration >= 12:
    score += 5

score = max(0, min(100, score))
```

---

# 🔍 Explainability Layer

Each score includes reasoning metadata.

Example:

```json
{
  "access_score": 35,
  "reasons": [
    "3 branded step therapies required",
    "TB test mandatory",
    "6-month authorization duration"
  ]
}
```

---

# 📁 Updated Project Structure

```text
PolicyLens-AI/
│
├── data/
│   ├── raw_pdfs/                    # Input payer PDFs
│   ├── markdown/                    # Extracted markdown files
│   ├── chunks/                      # Chunk-level structured data
│   ├── processed/                   # Intermediate outputs
│   └── ground_truth/                # Benchmark files
│
├── ingestion/
│   ├── pdf_to_markdown.py           # PDF extraction
│   ├── markdown_cleaner.py          # Text normalization
│   └── metadata_parser.py           # File metadata extraction
│
├── chunking/
│   ├── semantic_chunker.py          # Heading/table/bullet chunking
│   ├── chunk_classifier.py          # Section type classification
│   ├── brand_mapper.py              # Brand-to-chunk mapping
│   └── universal_detector.py        # Shared policy detection
│
├── extraction/
│   ├── regex_extractors.py          # Deterministic extraction
│   ├── llm_extractors.py            # Gemini-based extraction
│   ├── retrieval_engine.py          # Parameter-specific retrieval
│   ├── logical_reasoner.py          # AND/OR interpretation
│   └── aggregation_engine.py        # Final parameter aggregation
│
├── scoring/
│   ├── restrictiveness_engine.py    # Restriction calculations
│   ├── access_score.py              # Final scoring logic
│   └── explainability.py            # Reason generation
│
├── prompts/
│   ├── extraction_prompts.py
│   ├── classification_prompts.py
│   └── reasoning_prompts.py
│
├── evaluation/
│   ├── extraction_metrics.py
│   ├── score_metrics.py
│   └── benchmark_runner.py
│
├── app/
│   ├── streamlit_app.py
│   ├── payer_dashboard.py
│   └── visualizations.py
│
├── notebooks/
│   ├── experimentation/
│   ├── prompt_testing/
│   └── scoring_analysis/
│
├── outputs/
│   ├── result.csv
│   ├── explanations.json
│   └── logs/
│
├── requirements.txt
├── README.md
└── .env
```

---

# 🚀 Getting Started

## Installation

```bash
git clone https://github.com/yourusername/PolicyLens-AI.git

cd PolicyLens-AI

pip install -r requirements.txt
```

---

# ⚙️ Environment Variables

```bash
GEMINI_API_KEY=your_api_key_here
MODEL_NAME=gemini-2.5-flash
LOG_LEVEL=INFO
```

---

# ▶️ Running the Pipeline

## Step 1 — PDF → Markdown

```bash
python ingestion/pdf_to_markdown.py
```

---

## Step 2 — Semantic Chunking

```bash
python chunking/semantic_chunker.py
```

---

## Step 3 — Chunk Classification & Brand Mapping

```bash
python chunking/brand_mapper.py
```

---

## Step 4 — Parameter Extraction

```bash
python extraction/llm_extractors.py
```

---

## Step 5 — Access Score Generation

```bash
python scoring/access_score.py
```

---

## Step 6 — Generate Final Submission

```bash
python evaluation/benchmark_runner.py
```

---

# 📊 Example Output Format

| Filename   | Brand   | Age  | Step Therapy   | TB Test | Access Score |
| ---------- | ------- | ---- | -------------- | ------- | ------------ |
| 330109.pdf | TREMFYA | >=18 | 1 branded step | Y       | 75           |

---

# 🤖 Technology Stack

| Layer           | Technology               |
| --------------- | ------------------------ |
| LLM             | Gemini 2.5 Flash         |
| PDF Parsing     | PyMuPDF                  |
| NLP             | Regex + LLM Hybrid       |
| Data Processing | Pandas                   |
| Retrieval       | Semantic Chunk Retrieval |
| Dashboard       | Streamlit                |
| Evaluation      | Custom benchmark metrics |

---

# 🎯 Key Features

✅ Semantic chunk intelligence
✅ Multi-brand policy handling
✅ Universal criteria mapping
✅ Retrieval-augmented extraction
✅ Logical AND/OR reasoning
✅ Explainable access scoring
✅ Scalable modular architecture
✅ Enterprise-grade pipeline

---

# 📈 Evaluation Metrics

The solution is evaluated on:

1. Extraction Accuracy
2. Access Score Accuracy
3. Logical Reasoning Quality
4. Edge Case Handling
5. Explainability & Transparency

---

# 🔮 Future Improvements

* Vector database integration
* Graph-based policy reasoning
* Multi-indication support
* Policy comparison engine
* Payer benchmarking dashboard
* Real-time policy monitoring

---

# 📚 References

* Gemini API Documentation
* Prior Authorization Policy Standards
* FDA Label Benchmarking Guidelines

---

# 📄 License

[Add License]

---

# ❤️ Built for Intelligent Pharma Market Access Analytics

**PolicyLens-AI** transforms unstructured payer policies into actionable access intelligence.

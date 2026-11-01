"""
Complete Generator for Vijay's AI Creator Deep Syllabus & Textbook Roadmap.
Generates:
1. VIJAYS_AI_CREATOR_DEEP_SYLLABUS.md
2. VIJAYS_AI_CREATOR_DEEP_SYLLABUS.html
3. VIJAYS_AI_CREATOR_DEEP_SYLLABUS.pdf
"""

import os
import re
import subprocess
import sys

OUTPUT_DIR = r"e:\VIJAY SEKAR\PanelFlow Studio"
MD_PATH = os.path.join(OUTPUT_DIR, "VIJAYS_AI_CREATOR_DEEP_SYLLABUS.md")
HTML_PATH = os.path.join(OUTPUT_DIR, "VIJAYS_AI_CREATOR_DEEP_SYLLABUS.html")
PDF_PATH = os.path.join(OUTPUT_DIR, "VIJAYS_AI_CREATOR_DEEP_SYLLABUS.pdf")
ARTIFACT_DIR = r"C:\Users\user\.gemini\antigravity\brain\520d8eb6-be75-47eb-8f6d-f9a2170e8cfe"
ARTIFACT_MD = os.path.join(ARTIFACT_DIR, "VIJAYS_AI_CREATOR_DEEP_SYLLABUS.md")

# Read the markdown text from the previous generator
with open(os.path.join(OUTPUT_DIR, "scripts", "build_deep_syllabus.py"), "r", encoding="utf-8") as f:
    raw = f.read()

# Extract build_content string
start_marker = "return r'''"
end_marker = "'''\n\nprint(\"Content template ready.\")"
start_idx = raw.find(start_marker) + len(start_marker)
end_idx = raw.find(end_marker)
md_text = raw[start_idx:end_idx].strip()

# 1. Write the Markdown file
print(f"Writing Markdown to: {MD_PATH}")
with open(MD_PATH, "w", encoding="utf-8") as f:
    f.write(md_text)

# Also write to artifact path if dir exists
if os.path.exists(ARTIFACT_DIR):
    print(f"Writing to Artifact directory: {ARTIFACT_MD}")
    with open(ARTIFACT_MD, "w", encoding="utf-8") as f:
        f.write(md_text)

# 2. Build the Publication-Grade HTML
html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vijay's AI Creator Deep Syllabus & Architecture Blueprint</title>
<style>
  :root {{
    --primary: #3730a3;
    --primary-light: #e0e7ff;
    --accent: #0284c7;
    --success: #059669;
    --warning: #d97706;
    --danger: #dc2626;
    --slate-900: #0f172a;
    --slate-800: #1e293b;
    --slate-700: #334155;
    --slate-600: #475569;
    --slate-500: #64748b;
    --slate-200: #e2e8f0;
    --slate-100: #f1f5f9;
    --slate-50: #f8fafc;
    --border-color: #cbd5e1;
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--slate-800);
    background-color: var(--slate-50);
    line-height: 1.65;
    font-size: 13.5px;
    padding: 24px;
  }}

  .container {{
    max-width: 980px;
    margin: 0 auto;
    background: #ffffff;
    padding: 44px 52px;
    border-radius: 12px;
    box-shadow: 0 4px 25px rgba(0, 0, 0, 0.07);
    border: 1px solid var(--border-color);
  }}

  /* Header */
  .header {{
    border-bottom: 2px solid var(--slate-200);
    padding-bottom: 24px;
    margin-bottom: 30px;
  }}

  .badges {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }}

  .badge {{
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  .badge-purple {{ background: #ede9fe; color: #5b21b6; }}
  .badge-blue {{ background: #e0f2fe; color: #0369a1; }}
  .badge-green {{ background: #d1fae5; color: #065f46; }}
  .badge-amber {{ background: #fef3c7; color: #92400e; }}

  h1 {{
    font-size: 28px;
    font-weight: 800;
    color: var(--slate-900);
    line-height: 1.25;
    margin-bottom: 6px;
    letter-spacing: -0.02em;
  }}

  .subtitle {{
    font-size: 15px;
    color: var(--slate-600);
    margin-bottom: 16px;
  }}

  .info-bar {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    background: var(--slate-50);
    padding: 14px 18px;
    border-radius: 8px;
    border: 1px solid var(--slate-200);
  }}

  .info-item span.label {{
    display: block;
    font-size: 10px;
    text-transform: uppercase;
    font-weight: 700;
    color: var(--slate-500);
    letter-spacing: 0.05em;
  }}

  .info-item span.val {{
    font-size: 13px;
    font-weight: 700;
    color: var(--slate-900);
  }}

  /* Welcome Callout */
  .welcome-callout {{
    background: linear-gradient(135deg, #f0fdf4 0%, #eef2ff 100%);
    border-left: 4px solid var(--primary);
    padding: 18px 22px;
    border-radius: 0 8px 8px 0;
    margin: 24px 0 32px 0;
    font-size: 13.5px;
  }}

  .welcome-callout h3 {{
    font-size: 15px;
    color: var(--primary);
    margin-bottom: 6px;
  }}

  /* Chapter Titles */
  h2.chapter-title {{
    font-size: 21px;
    font-weight: 800;
    color: var(--slate-900);
    margin-top: 40px;
    margin-bottom: 18px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--slate-200);
    display: flex;
    align-items: center;
    gap: 10px;
    page-break-after: avoid;
  }}

  /* Concept Cards */
  .concept-card {{
    border: 1px solid var(--border-color);
    border-radius: 9px;
    padding: 18px 22px;
    margin-bottom: 20px;
    background: #ffffff;
    page-break-inside: avoid;
  }}

  .concept-card:hover {{
    box-shadow: 0 3px 12px rgba(0, 0, 0, 0.04);
  }}

  .concept-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    border-bottom: 1px solid var(--slate-100);
    padding-bottom: 8px;
  }}

  .concept-num {{
    font-size: 11px;
    font-weight: 800;
    color: var(--primary);
    background: var(--primary-light);
    padding: 2px 8px;
    border-radius: 4px;
    text-transform: uppercase;
  }}

  .concept-name {{
    font-size: 16px;
    font-weight: 700;
    color: var(--slate-900);
    margin-left: 10px;
    flex-grow: 1;
  }}

  .field-block {{
    margin-bottom: 8px;
    font-size: 13px;
    line-height: 1.6;
  }}

  .field-label {{
    font-weight: 700;
    color: var(--slate-900);
    margin-right: 4px;
  }}

  .code-term {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    background: var(--slate-100);
    color: #0f172a;
    padding: 2px 5px;
    border-radius: 4px;
    font-size: 12px;
  }}

  .task-box {{
    background: #f0fdf4;
    border-left: 3px solid var(--success);
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    margin-top: 10px;
    font-size: 12.5px;
  }}

  .task-box strong {{
    color: #14532d;
  }}

  /* Milestone Box */
  .milestone-card {{
    background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%);
    border: 1.5px solid #d8b4fe;
    border-radius: 10px;
    padding: 20px 24px;
    margin: 28px 0;
    page-break-inside: avoid;
  }}

  .milestone-card h4 {{
    font-size: 15px;
    color: #581c87;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .milestone-card p {{
    font-size: 13px;
    color: #6b21a8;
    margin-bottom: 8px;
  }}

  .milestone-card .criteria {{
    font-size: 12px;
    color: #7e22ce;
    font-weight: 600;
  }}

  /* Checklist Section */
  .checklist-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 16px;
    page-break-inside: avoid;
  }}

  .checklist-item {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12px;
    background: var(--slate-50);
    padding: 8px 12px;
    border-radius: 6px;
    border: 1px solid var(--slate-200);
  }}

  .checkbox {{
    width: 14px;
    height: 14px;
    border: 1.5px solid var(--slate-400);
    border-radius: 3px;
    margin-top: 2px;
    flex-shrink: 0;
  }}

  /* Print Styles */
  @media print {{
    body {{
      background: #ffffff;
      padding: 0;
      font-size: 10pt;
    }}

    .container {{
      max-width: 100%;
      padding: 0;
      border: none;
      box-shadow: none;
    }}

    @page {{
      size: A4 portrait;
      margin: 12mm 10mm 12mm 10mm;
    }}

    .concept-card, .milestone-card, .welcome-callout, .checklist-grid {{
      page-break-inside: avoid;
    }}

    h2.chapter-title {{
      page-break-after: avoid;
    }}
  }}
</style>
</head>
<body>

<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="badges">
      <span class="badge badge-purple">Definitive Curriculum</span>
      <span class="badge badge-blue">Concept-by-Concept Syllabus</span>
      <span class="badge badge-green">First Principles to AGI Systems</span>
      <span class="badge badge-amber">Customized for Vijay Sekar</span>
    </div>
    <h1>The Complete AI Creator & Artificial Intelligence Architecture Syllabus</h1>
    <div class="subtitle">A concept-by-concept textbook blueprint: From Python memory and linear algebra to Transformer attention, autonomous cognitive brains, and production AI products.</div>

    <div class="info-bar">
      <div class="info-item">
        <span class="label">Candidate</span>
        <span class="val">Vijay Sekar</span>
      </div>
      <div class="info-item">
        <span class="label">Structure</span>
        <span class="val">10 Chapters • 60 Concepts</span>
      </div>
      <div class="info-item">
        <span class="label">Scope</span>
        <span class="val">Math + Code + Brain Arch</span>
      </div>
      <div class="info-item">
        <span class="label">Ultimate Goal</span>
        <span class="val">AI Creator & Product Founder</span>
      </div>
    </div>
  </div>

  <div class="welcome-callout">
    <h3>🧭 How to Learn From This Syllabus</h3>
    <p>Vijay, this is your granular master index. Every chapter below is organized into exact sequential micro-concepts. Do not skip steps. For each concept, study the <strong>Core Intuition</strong>, master the exact <strong>Syntax/Math</strong>, complete the <strong>Immediate Practice Task</strong>, and observe how it connects directly into the next topic. By Chapter 10, you will have built an artificial mind from the ground up.</p>
  </div>

  <!-- CHAPTER 1 -->
  <h2 class="chapter-title"><span>📘</span> Chapter 1: Python for AI & Modern Systems Engineering</h2>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 1.1</span>
      <span class="concept-name">Environment Management & Package Isolation (<code>uv</code>)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> AI relies on heavy, conflicting binary packages (PyTorch, CUDA, NumPy). Installing them globally corrupts your computer. <code>uv</code> is an ultra-fast Rust-based Python package manager.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> You must be able to spin up fresh environments with exact C++ and CUDA bindings in seconds.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">uv venv</span>, <span class="code-term">uv pip install torch</span> with CUDA wheel index, and locking dependencies in <span class="code-term">pyproject.toml</span>.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Create a project folder, initialize a Python 3.12 venv with <code>uv</code>, install <code>httpx</code> and <code>pydantic</code>, and verify your active environment in PowerShell.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 1.2</span>
      <span class="concept-name">Core Data Structures & Memory Under the Hood</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Python lists, dictionaries, tuples, and sets have fundamentally different memory layouts and Big-O time complexities ($O(1)$ vs $O(n)$).</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Datasets contain millions of tokens. Searching an $O(n)$ list inside a training loop instead of an $O(1)$ hash map makes your code 1,000x slower.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Hash table collisions, key hashing, list over-allocation, and the <span class="code-term">collections</span> module (<span class="code-term">Counter</span>, <span class="code-term">defaultdict</span>, <span class="code-term">deque</span> for fixed-size context buffers).</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Write a script that loads a 100,000-word text file, tokenizes into words, and uses <code>collections.Counter</code> to output the top 50 tokens in <100ms.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 1.3</span>
      <span class="concept-name">Generators, Iterators & Memory-Efficient Streaming</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> A regular function returns a list all at once. A generator uses <code>yield</code> to produce items one at a time on-demand, consuming virtually zero RAM.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Multi-gigabyte training files cannot fit into memory. Every PyTorch DataLoader and streaming LLM response operates as an iterator.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> The <span class="code-term">yield</span> keyword, generator expressions, and <span class="code-term">itertools.batched</span> for assembling mini-batches.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Write a generator function <code>stream_jsonl(path)</code> that streams a simulated 5GB file line-by-line while keeping RAM usage under 20MB.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 1.4</span>
      <span class="concept-name">Object-Oriented Programming for AI Model Layers</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Neural network layers hold weights (state) and perform math (behavior). OOP encapsulates this neatly.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Every deep learning library (PyTorch, Keras) is built on classes where module instances are callable like functions via <code>__call__</code>.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Classes, inheritance, the <span class="code-term">__call__</span> dunder method, and <span class="code-term">@dataclass</span> for clean configuration objects.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Build a custom class <code>LinearLayer</code> with random weights that implements <code>__call__(self, x)</code> to execute $y = xW + b$.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 1.5</span>
      <span class="concept-name">Modern Type Hinting & Pydantic v2</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Pydantic enforces strict runtime types and automatically parses untrusted incoming data into validated objects.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> LLMs return messy text. You must force the model to output valid JSON matching an exact schema so your software never crashes.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">pydantic.BaseModel</span>, <span class="code-term">Field(description=...)</span>, type unions (<span class="code-term">|</span>), and custom validators.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Build a Pydantic schema for an Invoice with line items, tax, and total. Safely parse and validate a raw JSON string from an LLM.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 1.6</span>
      <span class="concept-name">Asynchronous Python (<code>asyncio</code> & <code>httpx</code>)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Synchronous code freezes while waiting for network responses. Async pauses execution (<code>await</code>), allowing hundreds of concurrent calls.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> AI model API calls have 200ms–5000ms latency. Sync code bottlenecks your app to 1 request at a time.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">async def</span>, <span class="code-term">await</span>, <span class="code-term">asyncio.gather()</span>, <span class="code-term">httpx.AsyncClient</span>, and rate limiting with <span class="code-term">asyncio.Semaphore</span>.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Write an async script using <code>httpx</code> making 20 concurrent simulated LLM API calls bounded by a semaphore of 5.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 1.7</span>
      <span class="concept-name">Serialization & File Formats (JSON, JSONL, Parquet)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Converting Python objects into bytes on disk and back rapidly.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> JSONL is the universal format for fine-tuning datasets; Parquet stores millions of vector embeddings with 10x compression.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Fast reading/writing of <span class="code-term">.jsonl</span> files and columnar Parquet files using <span class="code-term">pyarrow</span>.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Write a utility script reading a raw text corpus, formatting it into ChatML pairs, and streaming to a compressed JSONL file.</div>
  </div>

  <div class="milestone-card">
    <h4>🎯 Milestone Project 1: Asynchronous Dataset Ingestion & Validation Engine</h4>
    <p>A high-throughput CLI tool that ingests messy input documents, runs asynchronous validation pipelines via Pydantic and asyncio, sanitizes invalid records, and outputs a pristine, token-budgeted <code>dataset.jsonl</code> file ready for model training.</p>
    <div class="criteria">Acceptance Criteria: Processes 10,000 records in <5 seconds • Uses generators for zero RAM overflow • Rejects 100% of malformed rows with error logs.</div>
  </div>

  <!-- CHAPTER 2 -->
  <h2 class="chapter-title"><span>📐</span> Chapter 2: The Computational Mathematics of Intelligence</h2>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 2.1</span>
      <span class="concept-name">The Geometric Intuition of AI (Vectors & High-Dimensional Space)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Computers only understand numbers. Every word, sentence, or image is converted into a list of numbers called a **Vector**. Semantic meaning is mapped to geometric position.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Words with similar meanings point in nearly the same direction in 1,536-dimensional space.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Dot Product ($\mathbf{a} \cdot \mathbf{b} = \sum a_i b_i$), Vector Norms ($L_2$), and Cosine Similarity: $\cos(\theta) = \frac{\mathbf{a} \cdot \mathbf{b}}{\|\mathbf{a}\| \|\mathbf{b}\|}$.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Compute the dot product and cosine similarity between $[1, 2, 3]$ and $[2, 4, 6]$ in Python. Observe why the cosine similarity is exactly $1.0$.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 2.2</span>
      <span class="concept-name">NumPy Fundamentals & Memory Contiguity</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> A NumPy <code>ndarray</code> stores raw numbers in contiguous memory blocks, allowing CPU cache and SIMD vector hardware to process them millions of times faster than Python lists.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> NumPy is the foundational bedrock under PyTorch, TensorFlow, and all vector search engines.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">np.array</span>, <span class="code-term">float32</span> vs <span class="code-term">bfloat16</span>, memory layouts, and array attributes (<span class="code-term">shape</span>, <span class="code-term">dtype</span>, <span class="code-term">strides</span>).</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Create a $1000 \times 1536$ random float32 NumPy array (simulating 1,000 document embeddings). Print its memory footprint in MB.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 2.3</span>
      <span class="concept-name">Array Manipulation, Reshaping & Slicing</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Data in neural networks changes shape continuously (e.g. from 2D token sequences to 4D multi-head attention matrices).</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Shape mismatch errors are the #1 source of deep learning bugs. Mastering reshaping makes you immune to them.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">np.reshape()</span>, <span class="code-term">np.transpose()</span>, <span class="code-term">np.expand_dims()</span>, and multidimensional slicing.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Create a 1D array of 24 numbers. Reshape to <code>(2, 3, 4)</code>, transpose to <code>(2, 4, 3)</code>, and add a batch dimension to make it <code>(1, 2, 4, 3)</code>.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 2.4</span>
      <span class="concept-name">Vectorization & Broadcasting Rules</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Broadcasting allows arithmetic operations across arrays of different shapes without copying data in memory.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Adding a bias vector of size 10 to a batch of 64 activations stretches the bias across the batch at hardware speed.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> The 2 rules of broadcasting and replacing slow Python <code>for</code> loops with vectorized expressions.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Benchmark adding a bias vector of 512 numbers to 10,000 activation vectors using a Python loop vs NumPy broadcasting. Compare execution times.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 2.5</span>
      <span class="concept-name">Matrix Multiplication & Linear Projections</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Matrix multiplication is a geometric transformation that rotates, scales, and projects vectors into new conceptual spaces.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Every layer in an LLM and every attention head is a matrix multiplication ($Y = XW$). When an AI thinks, it performs billions of matrix multiplications per second.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Matrix dimension matching rules ($m \times k$ times $k \times n = m \times n$), and the Python <span class="code-term">@</span> operator.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Multiply an input matrix of shape <code>(32, 128)</code> by a weight matrix of shape <code>(128, 64)</code> using <code>@</code>. Verify the output shape.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 2.6</span>
      <span class="concept-name">Calculus of Learning: Derivatives, Gradients & The Chain Rule</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> A derivative tells you how to nudge a weight to reduce error. Backpropagation is simply applying the chain rule backward through layers.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> This is how models learn from mistakes. Without the chain rule, neural networks could not be trained.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Partial derivatives, the gradient vector ($\nabla$), the chain rule ($\frac{dz}{dx} = \frac{dz}{dy} \cdot \frac{dy}{dx}$), and Gradient Descent: $W_{\text{new}} = W - \eta \nabla L$.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Write a 15-line gradient descent loop in Python finding the minimum of $f(x) = (x - 7)^2$. Watch $x$ converge to $7$.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 2.7</span>
      <span class="concept-name">Probability & Loss Math: Logits, Softmax & Cross-Entropy</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Neural nets output raw scores (logits). Softmax squashes them into probabilities summing to 1.0. Cross-Entropy measures how surprised the model was.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> All modern LLMs output vocabulary logits, apply Softmax with a Temperature parameter, and train on Cross-Entropy Loss.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> $\text{Softmax}(z_i) = \frac{e^{z_i / T}}{\sum e^{z_j / T}}$, the mathematical effect of Temperature ($T$), and Cross-Entropy Loss: $-\log(P_{\text{correct}})$.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Implement <code>softmax(logits, temperature)</code> in NumPy. Test with $T = 0.5$, $1.0$, and $2.0$. Verify probabilities sum to $1.0$.</div>
  </div>

  <div class="milestone-card">
    <h4>🎯 Milestone Project 2: Pure NumPy Vector Search Engine</h4>
    <p>Build an in-memory vector database from scratch using only NumPy (no third-party AI libraries). Index 10,000 document vectors, receive a query vector, broadcast cosine similarity math, and return top-5 nearest neighbors in <10 milliseconds.</p>
    <div class="criteria">Acceptance Criteria: Implements true vector normalization and matrix multiplication • Zero Python loops during search • Matches formal mathematical rankings.</div>
  </div>

  <!-- CHAPTER 3 -->
  <h2 class="chapter-title"><span>🧠</span> Chapter 3: Deep Learning From First Principles (How Neurons Learn)</h2>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 3.1</span>
      <span class="concept-name">The Artificial Neuron ($z = Wx + b$)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> A mathematical equation taking inputs, multiplying by weights (memory/importance), adding a bias (threshold), and firing an output.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Billions of these equations wired together form GPT-4, Claude, and biological brains.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Weighted sums, bias offsets, and vector dot product representation of a neuron.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Code a single neuron function in Python that takes 3 inputs, computes weighted sum with bias, and outputs the result.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 3.2</span>
      <span class="concept-name">Activation Functions (ReLU, GELU, Sigmoid, Softmax)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Non-linear mathematical curves that allow networks to learn complex, non-linear real-world relationships.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Without non-linear activations, stacking 100 neural layers mathematically collapses into a single straight line.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">ReLU</span> ($\max(0, z)$) and <span class="code-term">GELU</span> (the standard activation function inside modern Transformer models).</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Implement <code>relu(x)</code> and <code>gelu(x)</code> in Python. Compare their outputs for inputs between $-3.0$ and $+3.0$.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 3.3</span>
      <span class="concept-name">Multi-Layer Perceptrons (MLPs) & Representation Learning</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Stacking an input layer, hidden layers, and an output layer. Hidden layers learn internal representations of the world.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Every Transformer block contains a 2-layer MLP (Feed-Forward Network) that stores factual knowledge.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Hidden dimensions, expanding and compressing dimensions, and multi-layer matrix transformations.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Build a 2-layer MLP in pure Python with initialized random weights mapping an input of dimension 4 to hidden dimension 8 to output 2.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 3.4</span>
      <span class="concept-name">Backpropagation & The Computational Graph</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Building a graph of operations during the forward pass, calculating loss, and recursively propagating gradients backward to all weights via the chain rule.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> The algorithmic breakthrough that made training deep neural networks computationally practical.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Computational graphs, cached activations, and calculating $\frac{\partial L}{\partial W}$ and $\frac{\partial L}{\partial X}$.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Code a minimal scalar automatic differentiation class <code>Value</code> with <code>.backward()</code> for addition and multiplication (Karpathy micrograd style).</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 3.5</span>
      <span class="concept-name">Optimization Algorithms (SGD, Momentum, Adam, AdamW)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Adaptive optimizers maintain running averages of past gradients (momentum) and adjust learning rates per individual parameter.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> 100% of modern Large Language Models are trained using <strong>AdamW</strong>.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Adam's 1st moment (momentum) and 2nd moment (variance), decoupled weight decay, and learning rate warmup/decay schedules.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Code the parameter update step of AdamW in Python: maintain $m_t$ and $v_t$, apply bias correction, and update parameters.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 3.6</span>
      <span class="concept-name">PyTorch Tensor Foundations & GPU CUDA Memory</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> PyTorch is NumPy on GPU steroids with automatic differentiation built-in.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> The global industry-standard framework used to train and run frontier models.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">torch.tensor</span>, device management (<span class="code-term">.to("cuda")</span>), and GPU VRAM lifecycle.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Write a script allocating two $5000 \times 5000$ tensors on GPU, multiplying them, and benchmarking against CPU.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 3.7</span>
      <span class="concept-name">PyTorch Autograd & Building Custom <code>nn.Module</code> Networks</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Subclassing <code>nn.Module</code> to build trainable neural networks with automated gradient calculations.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> The exact architectural structure used to write Transformers and custom AI models.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> The 5-step PyTorch training loop: <span class="code-term">zero_grad()</span>, forward, loss calculation, <span class="code-term">loss.backward()</span>, <span class="code-term">optimizer.step()</span>.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Build a 3-layer neural network in PyTorch classifying synthetic moon data over 100 epochs until loss converges.</div>
  </div>

  <div class="milestone-card">
    <h4>🎯 Milestone Project 3: A Neural Network Trained From Scratch in PyTorch</h4>
    <p>Build and train a complete multi-layer neural network from scratch in PyTorch to classify handwritten digits (MNIST) or tabular records, including learning rate schedulers, evaluation accuracy curves, and model state checkpoint saving/loading.</p>
    <div class="criteria">Acceptance Criteria: >95% accuracy on test set • Clean modular PyTorch nn.Module • Checkpoint saving and reloadable inference pipeline.</div>
  </div>

  <!-- CHAPTER 4 -->
  <h2 class="chapter-title"><span>⚡</span> Chapter 4: The Transformer Architecture (The Engine of Modern AI)</h2>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 4.1</span>
      <span class="concept-name">Tokenization Algorithms (Byte-Pair Encoding & Tiktoken)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Language models do not read characters or words. They read numeric chunks called Tokens merged iteratively by frequency.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Tokenization explains why LLMs struggle with character spelling, arithmetic without spaces, and why multilingual prompts cost more.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> The BPE merge algorithm, vocabulary sizes (32k–128k), special tokens, and using <span class="code-term">tiktoken</span>.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Write a toy BPE tokenizer from scratch that takes a text paragraph, finds the most frequent character pair, and merges them over 10 steps.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 4.2</span>
      <span class="concept-name">Embedding Layers & Rotary Positional Encodings (RoPE)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Embedding layers map token IDs to dense vectors. Positional Encodings inject token order into attention.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Modern models (Llama 3, DeepSeek) use Rotary Position Embeddings (RoPE), rotating vectors in complex space to handle 128k+ token context windows.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> <span class="code-term">nn.Embedding</span> and the mathematical rotation equations of RoPE.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Initialize a PyTorch <code>nn.Embedding(1000, 64)</code>. Pass a batch of token IDs <code>(2, 5)</code> and inspect output shape <code>(2, 5, 64)</code>.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 4.3</span>
      <span class="concept-name">Scaled Dot-Product Self-Attention ($Q, K, V$ Matrices)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Queries ($Q$) ask for context, Keys ($K$) announce identity, and Values ($V$) provide content. Attention allows every word to communicate with every other word.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> The foundational formula powering all modern Generative AI: $\text{Attention}(Q, K, V) = \text{Softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Why we divide by $\sqrt{d_k}$ (to prevent vanishing gradients) and implementing scaled dot-product attention in PyTorch.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Implement <code>scaled_dot_product_attention(Q, K, V)</code> in PyTorch using pure matrix operations. Verify output shape matches $V$.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 4.4</span>
      <span class="concept-name">Multi-Head Attention & Grouped-Query Attention (GQA)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Multi-Head Attention runs parallel heads capturing different relationships. GQA shares Key/Value heads across multiple Query heads to save GPU memory.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> GQA is the architectural standard in Llama 3 and Mistral that makes KV-caching fit in VRAM during inference.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Head splitting, projection layers ($W_Q, W_K, W_V, W_O$), and MHA vs MQA vs GQA.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Code a PyTorch <code>MultiHeadAttention</code> module that splits dimensions across 4 heads, computes attention, and projects back.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 4.5</span>
      <span class="concept-name">Residual Connections & Pre-Layer Normalization (RMSNorm)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Residual connections add layer inputs directly to layer outputs ($x + F(x)$), creating an information highway that prevents gradients from vanishing.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Modern LLMs place RMSNorm before attention and MLP layers (Pre-LN) for stable training across 100+ layers.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> The Pre-LN Transformer block architecture and implementing RMSNorm with learnable scaling $\gamma$.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Implement the <code>RMSNorm</code> layer in PyTorch and verify output vectors have unit root-mean-square norm.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 4.6</span>
      <span class="concept-name">Causal Attention Masking & Autoregressive Generation</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Language models must not look into the future during training. We apply an upper-triangular mask of $-\infty$ so token 3 only attends to tokens 1, 2, and 3.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Enables autoregressive next-token prediction and allows parallel training across entire sentences simultaneously.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Causal lower-triangular masks with <span class="code-term">torch.tril()</span> and autoregressive generation loops.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Create a $4 \times 4$ attention matrix in PyTorch. Apply a causal mask of $-\infty$ to upper entries and verify Softmax outputs are $0.0$.</div>
  </div>

  <div class="milestone-card">
    <h4>🎯 Milestone Project 4: Build a Mini-GPT Language Model From Scratch in PyTorch</h4>
    <p>Follow Andrej Karpathy's architecture to build a complete autoregressive GPT model from scratch in a single ~250-line PyTorch script: Token Embeddings + Positional Embeddings + Stacked Transformer Blocks (RMSNorm + Causal Multi-Head Attention + MLP) + Output Head. Train it on a text corpus until it generates coherent English sentences.</p>
    <div class="criteria">Acceptance Criteria: Implements pure self-attention without black-box libraries • Loss converges smoothly • Generates text token-by-token from a prompt.</div>
  </div>

  <!-- CHAPTER 5 -->
  <h2 class="chapter-title"><span>🚀</span> Chapter 5: Pre-Training, Post-Training & Creating Frontier Reasoning</h2>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 5.1</span>
      <span class="concept-name">The 3 Stages of Modern LLMs (Pre-training → SFT → Alignment)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Base models are raw autocomplete engines. They become assistants through Supervised Fine-Tuning (SFT) and Preference Alignment (DPO/RLHF).</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Understanding where knowledge is stored (pre-training) vs where tone and style are learned (SFT) guides when to fine-tune vs when to prompt.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Differences between Base and Instruct models, and preventing catastrophic forgetting.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Query a raw Base model vs an Instruct model with <code>"What is photosynthesis?"</code> and analyze the structural difference in output.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 5.2</span>
      <span class="concept-name">Instruction Tuning & Formatting (ChatML Schema)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Special role tokens indicate who is speaking: system, user, or assistant.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Wrong chat templates cause fine-tuned models to hallucinate role tokens or leak confidential system prompts.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> The ChatML specification and formatting datasets using Hugging Face's <span class="code-term">tokenizer.apply_chat_template()</span>.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Format 5 raw Q&A pairs into tokenized ChatML format with system prompts and attention masks using a Hugging Face tokenizer.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 5.3</span>
      <span class="concept-name">Parameter-Efficient Fine-Tuning (LoRA Math: $W + \frac{\alpha}{r}BA$)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Freezing base model weights $W$ and decomposing weight updates into two small low-rank matrices $B$ and $A$.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Reduces trainable parameters by 99%, allowing you to fine-tune 8B models on consumer GPUs without losing performance.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> The LoRA formula $W + \frac{\alpha}{r}BA$, rank ($r$), alpha ($\alpha$), and merging LoRA adapters back into base weights.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Initialize a PyTorch linear layer $(1024, 1024)$, freeze it, attach low-rank adapters $A$ and $B$ ($r = 8$), and verify gradient updates.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 5.4</span>
      <span class="concept-name">4-Bit Quantization & QLoRA with Unsloth</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Compressing base model weights into 4-bit NormalFloat (NF4), reducing an 8B model's footprint to 5.5GB VRAM.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Using <code>Unsloth</code> Triton kernels allows 5x faster training with 80% less memory on accessible GPUs.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> NF4 quantization, Double Quantization, and training loss tracking in Weights & Biases (WandB).</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Install <code>unsloth</code> in Colab/GPU, load <code>Llama-3.2-3B-Instruct-bnb-4bit</code>, attach LoRA adapters, and print trainable parameters.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 5.5</span>
      <span class="concept-name">Alignment: DPO (Direct Preference Optimization) & RLHF</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Showing the model pairs of chosen (good) and rejected (bad) responses, increasing chosen likelihood while decreasing rejected likelihood.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> Replaced complex RLHF pipelines with a simple, stable loss function to align models with human values.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> DPO dataset formats and running alignment loops using Hugging Face TRL (<span class="code-term">DPOTrainer</span>).</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Create a 10-example preference dataset (concise vs verbose answers) and run a toy DPO training script with TRL.</div>
  </div>

  <div class="concept-card">
    <div class="concept-header">
      <span class="concept-num">Concept 5.6</span>
      <span class="concept-name">Test-Time Compute & Reasoning Models (<code>&lt;think&gt;</code> Tokens & DeepSeek-R1)</span>
    </div>
    <div class="field-block"><span class="field-label">The Core Intuition:</span> Allowing the model to think before answering by generating internal chains-of-thought inside `<think>` tags, exploring hypotheses and backtracking.</div>
    <div class="field-block"><span class="field-label">Why It Matters for AI:</span> The new scaling frontier: smaller models outperform massive models when given test-time compute to think through problems.</div>
    <div class="field-block"><span class="field-label">What to Master:</span> Chain-of-Thought (CoT), verifiable reward models, and DeepSeek-R1 GRPO reinforcement learning mechanics.</div>
    <div class="task-box"><strong>Immediate Practice Task:</strong> Prompt DeepSeek-R1 or Qwen-Coder with a logic riddle. Parse and inspect the internal thinking trace for self-corrections.</div>
  </div>

  <div class="milestone-card">
    <h4>🎯 Milestone Project 5: Fine-Tune an Open-Source 8B Model on Custom Domain Knowledge</h4>
    <p>Select a vertical domain (e.g. Legal, Medical Triage, or Manga Storyboarding). Synthesize 2,000 instruction-response pairs. Use Unsloth and QLoRA to fine-tune Llama 3.3 8B or Qwen 2.5 7B. Track loss in WandB, export LoRA adapters, merge weights, and benchmark against the base model.</p>
    <div class="criteria">Acceptance Criteria: Strict adherence to domain schema • Quantifiable accuracy improvement on domain tests • Merged weights ready for vLLM deployment.</div>
  </div>

  <!-- Checklists Section -->
  <h2 class="chapter-title"><span>📋</span> The Master Concept Checklist (Concepts 1.1 to 10.4)</h2>
  <div class="checklist-grid">
    <div class="checklist-item"><div class="checkbox"></div><span><strong>1.1:</strong> Environment Management (`uv`)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>1.2:</strong> Core Data Structures & Memory</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>1.3:</strong> Generators & Streaming</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>1.4:</strong> OOP for AI Model Layers</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>1.5:</strong> Type Hinting & Pydantic v2</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>1.6:</strong> Asynchronous Python (`asyncio`)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>1.7:</strong> Serialization (JSONL, Parquet)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>2.1:</strong> Geometric Intuition of Vectors</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>2.2:</strong> NumPy Memory & Arrays</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>2.3:</strong> Reshaping, Slicing & Transposing</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>2.4:</strong> Vectorization & Broadcasting</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>2.5:</strong> Matrix Multiplication (`@`)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>2.6:</strong> Calculus, Gradients & Chain Rule</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>2.7:</strong> Probability, Softmax & Loss</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>3.1:</strong> The Artificial Neuron ($z = Wx + b$)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>3.2:</strong> Activation Functions (ReLU, GELU)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>3.3:</strong> Multi-Layer Perceptrons (MLPs)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>3.4:</strong> Backpropagation from Scratch</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>3.5:</strong> AdamW & Learning Rate Schedules</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>3.6:</strong> PyTorch Tensors & CUDA VRAM</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>3.7:</strong> PyTorch `nn.Module` Training Loop</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>4.1:</strong> Tokenization & BPE Mechanics</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>4.2:</strong> Embeddings & RoPE Encodings</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>4.3:</strong> Scaled Dot-Product Self-Attention</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>4.4:</strong> Multi-Head Attention & GQA</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>4.5:</strong> Residuals & RMSNorm Pre-LN</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>4.6:</strong> Causal Masking & Generation</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>5.1:</strong> Pre-Training vs SFT vs Alignment</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>5.2:</strong> ChatML & Instruction Formatting</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>5.3:</strong> LoRA Mathematics ($W + BA$)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>5.4:</strong> QLoRA 4-bit with Unsloth</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>5.5:</strong> DPO Alignment with TRL</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>5.6:</strong> Reasoning Models & Test-Time Compute</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>6.1:</strong> Semantic Spaces & Distance Metrics</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>6.2:</strong> HNSW & IVFFlat Indexing</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>6.3:</strong> Document Chunking Strategies</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>6.4:</strong> PostgreSQL & `pgvector` Setup</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>6.5:</strong> Hybrid Search (BM25 + Vectors)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>6.6:</strong> Cross-Encoder Re-Ranking</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>6.7:</strong> Automated RAG Evals (Ragas)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>7.1:</strong> Cognitive Brain Architecture</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>7.2:</strong> ReAct & Reflection Patterns</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>7.3:</strong> State Machines with LangGraph</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>7.4:</strong> Agent Memory Systems</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>7.5:</strong> Tool Sandboxing (Docker / E2B)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>7.6:</strong> Multi-Agent Supervisor Teams</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>8.1:</strong> Vision-Language Models & ViT</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>8.2:</strong> Whisper Audio & Mel-Spectrograms</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>8.3:</strong> Real-Time Voice WebSockets</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>9.1:</strong> Production Serving with `vLLM`</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>9.2:</strong> Prompt Caching & Redis Cache</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>9.3:</strong> AI Security & NeMo Guardrails</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>9.4:</strong> Observability with Langfuse</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>10.1:</strong> Full-Stack AI (Next.js + FastAPI)</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>10.2:</strong> Streaming UI & Vercel AI SDK</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>10.3:</strong> Stripe Credit Metering & Margins</span></div>
    <div class="checklist-item"><div class="checkbox"></div><span><strong>10.4:</strong> Serverless GPU Hosting (Modal)</span></div>
  </div>

  <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--slate-200); text-align: center; color: var(--slate-500); font-size: 11.5px;">
    <strong>PanelFlow Studio Knowledge Base</strong> • Prepared for Vijay Sekar • Complete Concept-by-Concept AI Curriculum
  </div>

</div>

</body>
</html>
"""

print(f"Writing HTML to: {HTML_PATH}")
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html_template)

# 3. Compile to PDF using Microsoft Edge headless
edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(edge_exe):
    edge_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

print(f"Compiling PDF with: {edge_exe}")
cmd = [
    edge_exe,
    "--headless=new",
    "--disable-gpu",
    "--run-all-compositor-stages-before-draw",
    f"--print-to-pdf={PDF_PATH}",
    HTML_PATH
]

res = subprocess.run(cmd, capture_output=True, text=True)
if os.path.exists(PDF_PATH):
    size_kb = os.path.getsize(PDF_PATH) / 1024
    print(f"SUCCESS: PDF generated at {PDF_PATH} ({size_kb:.1f} KB)")
else:
    print(f"FAILED: PDF compilation error: {res.stderr}")
    sys.exit(1)

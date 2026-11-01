"""
Compiles Vijay's complete syllabus to Markdown, HTML, and PDF.
"""

import os
import subprocess
import sys

# Let's read the markdown directly from build_deep_syllabus.py
with open(r"e:\VIJAY SEKAR\PanelFlow Studio\scripts\build_deep_syllabus.py", "r", encoding="utf-8") as f:
    text = f.read()

start_marker = "return r'''"
end_marker = "'''\n\nprint(\"Content template ready.\")"
s = text.find(start_marker) + len(start_marker)
e = text.find(end_marker)
md_content = text[s:e].strip()

# Write Markdown
md_out = r"e:\VIJAY SEKAR\PanelFlow Studio\VIJAYS_AI_CREATOR_DEEP_SYLLABUS.md"
with open(md_out, "w", encoding="utf-8") as f:
    f.write(md_content)
print(f"Wrote MD: {md_out}")

# Write to Artifacts
artifact_path = r"C:\Users\user\.gemini\antigravity\brain\520d8eb6-be75-47eb-8f6d-f9a2170e8cfe\VIJAYS_AI_CREATOR_DEEP_SYLLABUS.md"
with open(artifact_path, "w", encoding="utf-8") as f:
    f.write(md_content)
print(f"Wrote Artifact: {artifact_path}")

target = """                try:
                    project_service.confirm_ocr(db, self.project_id)
                except Exception as e:
                    self.log(f"OCR note: {e} (proceeding with panel order baseline)")"""

replacement = """                try:
                    project_service.confirm_ocr(db, self.project_id)
                except Exception as e:
                    self.log(f"OCR note: {e} (proceeding with panel order baseline)")

                # Automated Watermark & Ad Keyword Blurring
                try:
                    from engine.imaging.sanitizer import auto_sanitize_project_panels
                    self.log("OCR Stage: Scanning and auto-blurring promotional watermarks & keywords...")
                    blur_res = auto_sanitize_project_panels(self.project_id, db=db)
                    if blur_res.get("total_blurred_regions", 0) > 0:
                        self.log(f"OCR Stage: Auto-blurred {blur_res['total_blurred_regions']} watermark regions across {blur_res['panels_affected']} panels.")
                except Exception as e:
                    self.log(f"OCR Stage watermark sanitizer note: {e}")"""

with open(r'engine\pipeline\autopilot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Normalize CRLF to LF for replacement, then write back
normalized_text = text.replace('\r\n', '\n')
norm_target = target.replace('\r\n', '\n')
norm_replacement = replacement.replace('\r\n', '\n')

if norm_target in normalized_text and 'auto_sanitize_project_panels' not in normalized_text:
    new_text = normalized_text.replace(norm_target, norm_replacement, 1)
    with open(r'engine\pipeline\autopilot.py', 'w', encoding='utf-8') as f:
        f.write(new_text)
    print("Successfully patched autopilot with auto_sanitize_project_panels!")
else:
    print("Could not match target or already patched.")

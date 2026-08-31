import os
import re
import json
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dotenv import load_dotenv
from pypdf import PdfReader
import anthropic


# ============================================================
# ENVIRONMENT / ANTHROPIC CONFIGURATION
# ============================================================

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY was not found.\n"
        "Please create a .env file containing:\n\n"
        "ANTHROPIC_API_KEY=your_api_key_here"
    )

client = anthropic.Anthropic(
    api_key=API_KEY,
    base_url="https://api.anthropic.com"
)


# ============================================================
# MODEL CONFIGURATION
# ============================================================

MODEL_CONFIG = {
    "Claude 5 Sonnet": {
        "id": "claude-sonnet-5",
        "icon": "🧠"
    },

    "Claude 4.5 Haiku": {
        "id": "claude-haiku-4-5-20251001",
        "icon": "⚡"
    },

    "Claude 4.8 Opus": {
        "id": "claude-opus-4-8",
        "icon": "💎"
    }
}


# ============================================================
# CANONICAL MEDICAL CONSENT RISK CATEGORIES
# ============================================================

RISK_CATEGORIES = [
    "procedure risks",
    "bleeding",
    "infection",
    "pain",
    "swelling",
    "scarring",
    "anesthesia risks",
    "allergic reaction",
    "nerve damage",
    "organ damage",
    "blood clots",
    "breathing complications",
    "cardiac complications",
    "unexpected complications",
    "death",
    "need for additional treatment",
    "treatment failure",
    "alternative treatments",
    "no treatment option",
    "benefits and limitations",
    "confidentiality and privacy",
    "medical data sharing",
    "withdrawal or refusal rights",
    "financial responsibility",
    "follow-up requirements"
]


# ============================================================
# CLAUDE API FUNCTION
# ============================================================

def ask_claude_api(prompt, model_target, system_message=""):
    """
    Sends a request to Anthropic's Messages API and extracts
    text content from the returned content blocks.
    """

    try:

        response = client.messages.create(
            model=model_target,
            max_tokens=500,
            system=system_message,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        text_blocks = []

        for block in response.content:

            if block.type == "text":
                text_blocks.append(block.text)

        if text_blocks:
            return "\n".join(text_blocks)

        return "No text response received."

    except Exception as e:

        return f"API_ERROR: {str(e)}"


# ============================================================
# PII ANONYMIZATION
# ============================================================

def clean_pii_data(text):
    """
    Local anonymization before sending consent-form text
    to the cloud API.
    """

    # Full name
    text = re.sub(
        r"(?im)^\s*Full\s*Name\s*:\s*[^\n]+",
        "Full Name: [REDACTED_PATIENT_NAME]",
        text
    )

    # Date of Birth
    text = re.sub(
        r"(?im)^\s*Date\s*of\s*Birth\s*:\s*[^\n]+",
        "Date of Birth: [REDACTED_DATE_OF_BIRTH]",
        text
    )

    # Phone number
    text = re.sub(
        r"(?i)(phone|mobile|telephone|contact\s*number)\s*:\s*[^\n]+",
        r"\1: [REDACTED_PHONE_NUMBER]",
        text
    )

    # Indian phone numbers
    text = re.sub(
        r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b",
        "[REDACTED_PHONE_NUMBER]",
        text
    )

    # Email
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[REDACTED_EMAIL]",
        text
    )

    # Address
    text = re.sub(
        r"(?im)^\s*Address\s*:\s*[^\n]+",
        "Address: [REDACTED_ADDRESS]",
        text
    )

    # Indian PIN code
    text = re.sub(
        r"\b[1-9][0-9]{5}\b",
        "[REDACTED_PIN]",
        text
    )

    # Explicit DOB formats
    text = re.sub(
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
        "[REDACTED_DATE]",
        text
    )

    text = re.sub(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[a-z]*\s+\d{2,4}\b",
        "[REDACTED_DATE]",
        text,
        flags=re.IGNORECASE
    )

    return text


# ============================================================
# PDF / TXT UPLOAD
# ============================================================

def browse_file():

    file_path = filedialog.askopenfilename(
        title="Select Consent Form / Privacy Document",
        filetypes=[
            ("All Supported Forms", "*.pdf *.txt"),
            ("PDF Documents", "*.pdf"),
            ("Text Files", "*.txt"),
            ("All Files", "*.*")
        ]
    )

    if not file_path:
        return

    filename = os.path.basename(file_path)
    extension = os.path.splitext(filename)[1].lower()

    try:

        if extension == ".pdf":

            reader = PdfReader(file_path)

            extracted_text = ""

            for page in reader.pages:

                page_text = page.extract_text()

                if page_text:
                    extracted_text += page_text + "\n"

            if not extracted_text.strip():

                messagebox.showwarning(
                    "Empty Document",
                    "Could not extract readable text from this PDF."
                )

                return

        else:

            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as file:

                extracted_text = file.read()

        text_input.delete("1.0", tk.END)
        text_input.insert(tk.END, extracted_text.strip())

        status_label.config(
            text=f"Uploaded: {filename}",
            fg="green"
        )

    except Exception as e:

        messagebox.showerror(
            "Upload Error",
            f"Could not read the document:\n\n{e}"
        )


# ============================================================
# EXTRACT TEXT FROM CLAUDE RESPONSE
# ============================================================

def extract_json_from_response(response_text):

    """
    Attempts to extract JSON even if Claude surrounds
    the JSON with markdown code fences.
    """

    try:

        return json.loads(response_text)

    except json.JSONDecodeError:
        pass

    # Remove markdown code fences
    cleaned = response_text.replace("```json", "")
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.strip()

    try:

        return json.loads(cleaned)

    except json.JSONDecodeError:
        pass

    # Search for JSON object
    match = re.search(
        r"\{.*\}",
        cleaned,
        re.DOTALL
    )

    if match:

        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ============================================================
# NORMALIZE RISK NAMES
# ============================================================

def normalize_risk(risk):

    risk = risk.lower().strip()

    # Remove punctuation
    risk = re.sub(r"[^a-z0-9\s]", "", risk)

    # Match against canonical categories
    for category in RISK_CATEGORIES:

        category_clean = re.sub(
            r"[^a-z0-9\s]",
            "",
            category.lower()
        )

        if (
            category_clean in risk
            or risk in category_clean
        ):
            return category

    return risk


# ============================================================
# MODEL ANALYSIS
# ============================================================

def analyze_model(model_name, model_id, anonymized_text):

    system_prompt = f"""
You are a medical consent document analysis AI.

Analyze the supplied consent document.

Your task is to identify the risks and important consent elements
that are actually relevant to this document.

Use ONLY the following standardized risk categories:

{json.dumps(RISK_CATEGORIES, indent=2)}

Return ONLY valid JSON.

Required format:

{{
    "summary": "One concise sentence explaining what the patient is agreeing to.",
    "sensitive_elements": [
        "element 1",
        "element 2"
    ],
    "risks": [
        "procedure risks",
        "infection"
    ],
    "red_flags": [
        "important concern 1"
    ]
}}

IMPORTANT:

- Only include risk categories that are relevant to the document.
- Do not invent risks that are not reasonably applicable.
- Use the exact risk-category names supplied above.
- Keep the response concise.
"""

    user_prompt = (
        "Analyze the following anonymized medical consent form:\n\n"
        + anonymized_text
    )

    start_time = time.perf_counter()

    raw_response = ask_claude_api(
        user_prompt,
        model_id,
        system_message=system_prompt
    )

    elapsed_time = time.perf_counter() - start_time

    parsed = extract_json_from_response(raw_response)

    if parsed is None:

        return {
            "model": model_name,
            "time": elapsed_time,
            "risks": [],
            "summary": raw_response,
            "sensitive_elements": [],
            "red_flags": [],
            "error": True
        }

    risks = parsed.get("risks", [])

    normalized_risks = set()

    for risk in risks:

        normalized_risks.add(
            normalize_risk(str(risk))
        )

    return {
        "model": model_name,
        "time": elapsed_time,
        "risks": normalized_risks,
        "summary": parsed.get("summary", ""),
        "sensitive_elements": parsed.get(
            "sensitive_elements",
            []
        ),
        "red_flags": parsed.get(
            "red_flags",
            []
        ),
        "error": False
    }


# ============================================================
# COMPARATIVE ANALYSIS
# ============================================================

def calculate_comparison(results):

    """
    Missing Risks is calculated relative to the union of risks
    identified by all selected models.
    """

    all_risks = set()

    for result in results:

        all_risks.update(
            result["risks"]
        )

    for result in results:

        missing = all_risks - result["risks"]

        result["missing_risks"] = len(missing)
        result["missing_risk_list"] = sorted(missing)

    return results


# ============================================================
# DISPLAY COMPARISON TABLE
# ============================================================

def display_comparison_table(results):

    # ========================================================
    # CLEAR PREVIOUS OUTPUT
    # ========================================================

    for widget in frame_output_container.winfo_children():
        widget.destroy()

    # ========================================================
    # SCROLLABLE OUTPUT AREA
    # ========================================================

    output_canvas = tk.Canvas(
        frame_output_container,
        highlightthickness=0,
        bg="white"
    )

    output_scrollbar = ttk.Scrollbar(
        frame_output_container,
        orient="vertical",
        command=output_canvas.yview
    )

    output_canvas.configure(
        yscrollcommand=output_scrollbar.set
    )

    output_scrollbar.pack(
        side=tk.RIGHT,
        fill=tk.Y
    )

    output_canvas.pack(
        side=tk.LEFT,
        fill=tk.BOTH,
        expand=True
    )

    # Frame that will contain ALL generated content
    scrollable_frame = tk.Frame(
        output_canvas,
        bg="white"
    )

    canvas_window = output_canvas.create_window(
        (0, 0),
        window=scrollable_frame,
        anchor="nw"
    )

    # ========================================================
    # UPDATE SCROLL REGION
    # ========================================================

    def update_scroll_region(event=None):

        output_canvas.configure(
            scrollregion=output_canvas.bbox("all")
        )

    scrollable_frame.bind(
        "<Configure>",
        update_scroll_region
    )

    # Make inner frame width follow canvas width
    def resize_inner_frame(event):

        output_canvas.itemconfig(
            canvas_window,
            width=event.width
        )

    output_canvas.bind(
        "<Configure>",
        resize_inner_frame
    )

    # ========================================================
    # MOUSE WHEEL SUPPORT
    # ========================================================

    def mousewheel(event):

        output_canvas.yview_scroll(
            int(-1 * (event.delta / 120)),
            "units"
        )

    output_canvas.bind_all(
        "<MouseWheel>",
        mousewheel
    )

    # ========================================================
    # TITLE
    # ========================================================

    comparison_title = tk.Label(
        scrollable_frame,
        text="📊 Compare Models",
        font=("Arial", 20, "bold"),
        fg="#1f4e79",
        bg="white"
    )

    comparison_title.pack(
        anchor=tk.W,
        pady=(5, 12),
        padx=5
    )

    # ========================================================
    # COMPARISON TABLE
    # ========================================================

    table_frame = tk.Frame(
        scrollable_frame,
        bd=1,
        relief=tk.SOLID,
        bg="white"
    )

    table_frame.pack(
        fill=tk.X,
        padx=5
    )

    style = ttk.Style()

    style.configure(
        "Comparison.Treeview",
        font=("Arial", 10),
        rowheight=42
    )

    style.configure(
        "Comparison.Treeview.Heading",
        font=("Arial", 10, "bold")
    )

    columns = (
        "model",
        "time",
        "missing"
    )

    tree = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        style="Comparison.Treeview",
        height=len(results)
    )

    tree.heading(
        "model",
        text="Model"
    )

    tree.heading(
        "time",
        text="Time (sec)"
    )

    tree.heading(
        "missing",
        text="Missing Risks"
    )

    tree.column(
        "model",
        width=450,
        anchor=tk.W
    )

    tree.column(
        "time",
        width=250,
        anchor=tk.CENTER
    )

    tree.column(
        "missing",
        width=250,
        anchor=tk.CENTER
    )

    for result in results:

        icon = MODEL_CONFIG[
            result["model"]
        ]["icon"]

        tree.insert(
            "",
            tk.END,
            values=(
                f"{icon}  {result['model']}",
                f"{result['time']:.2f}",
                result["missing_risks"]
            )
        )

    tree.pack(
        fill=tk.X,
        expand=True
    )

    # ========================================================
    # OVERALL COMPARISON
    # ========================================================

    if results:

        fastest = min(
            results,
            key=lambda x: x["time"]
        )

        best_risk_model = min(
            results,
            key=lambda x: x["missing_risks"]
        )

        summary_frame = tk.Frame(
            scrollable_frame,
            bg="white"
        )

        summary_frame.pack(
            fill=tk.X,
            pady=10,
            padx=5
        )

        tk.Label(
            summary_frame,
            text=(
                f"⚡ Fastest: {fastest['model']} "
                f"({fastest['time']:.2f} sec)"
            ),
            font=("Arial", 10, "bold"),
            fg="#555555",
            bg="white"
        ).pack(
            side=tk.LEFT,
            padx=10
        )

        tk.Label(
            summary_frame,
            text=(
                f"🛡 Lowest Missing Risks: "
                f"{best_risk_model['model']} "
                f"({best_risk_model['missing_risks']})"
            ),
            font=("Arial", 10, "bold"),
            fg="#228B22",
            bg="white"
        ).pack(
            side=tk.LEFT,
            padx=10
        )

    # ========================================================
    # DETAILED ANALYSIS TITLE
    # ========================================================

    details_label = tk.Label(
        scrollable_frame,
        text="📋 Detailed Model Analysis",
        font=("Arial", 14, "bold"),
        fg="#1f4e79",
        bg="white"
    )

    details_label.pack(
        anchor=tk.W,
        pady=(5, 8),
        padx=5
    )

    # ========================================================
    # INDIVIDUAL MODEL RESULTS
    # ========================================================

    for result in results:

        model_frame = tk.LabelFrame(
            scrollable_frame,
            text=(
                f"{MODEL_CONFIG[result['model']]['icon']} "
                f"{result['model']}"
            ),
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8,
            bg="white"
        )

        model_frame.pack(
            fill=tk.X,
            padx=5,
            pady=5
        )

        # ----------------------------------------------------
        # TIME
        # ----------------------------------------------------

        tk.Label(
            model_frame,
            text=f"⏱ Response Time: {result['time']:.2f} seconds",
            font=("Arial", 9, "bold"),
            bg="white"
        ).pack(
            anchor=tk.W,
            pady=(0, 5)
        )

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        tk.Label(
            model_frame,
            text="🎯 Summary",
            font=("Arial", 9, "bold"),
            fg="#1f4e79",
            bg="white"
        ).pack(
            anchor=tk.W
        )

        summary_text = tk.Text(
            model_frame,
            height=3,
            font=("Arial", 9),
            wrap=tk.WORD,
            bg="#f8f9fa",
            relief=tk.SOLID,
            bd=1
        )

        summary_text.insert(
            tk.END,
            result["summary"]
        )

        summary_text.config(
            state=tk.DISABLED
        )

        summary_text.pack(
            fill=tk.X,
            pady=(2, 6)
        )

        # ----------------------------------------------------
        # RISKS IDENTIFIED
        # ----------------------------------------------------

        tk.Label(
            model_frame,
            text="🔍 Risks Identified",
            font=("Arial", 9, "bold"),
            fg="#1f4e79",
            bg="white"
        ).pack(
            anchor=tk.W
        )

        risks_text = "\n".join(
            f"• {risk}"
            for risk in sorted(result["risks"])
        )

        if not risks_text:
            risks_text = "None identified."

        risks_box = tk.Text(
            model_frame,
            height=max(3, min(8, len(result["risks"]) + 1)),
            font=("Arial", 9),
            wrap=tk.WORD,
            bg="#f8f9fa",
            relief=tk.SOLID,
            bd=1
        )

        risks_box.insert(
            tk.END,
            risks_text
        )

        risks_box.config(
            state=tk.DISABLED
        )

        risks_box.pack(
            fill=tk.X,
            pady=(2, 6)
        )

        # ----------------------------------------------------
        # MISSING RISKS
        # ----------------------------------------------------

        tk.Label(
            model_frame,
            text=(
                f"⚠️ Missing Risks "
                f"({result['missing_risks']})"
            ),
            font=("Arial", 9, "bold"),
            fg="#b22222",
            bg="white"
        ).pack(
            anchor=tk.W
        )

        missing_text = "\n".join(
            f"• {risk}"
            for risk in result["missing_risk_list"]
        )

        if not missing_text:
            missing_text = "None."

        missing_box = tk.Text(
            model_frame,
            height=max(
                3,
                min(
                    8,
                    len(result["missing_risk_list"]) + 1
                )
            ),
            font=("Arial", 9),
            wrap=tk.WORD,
            bg="#fff8f8",
            relief=tk.SOLID,
            bd=1
        )

        missing_box.insert(
            tk.END,
            missing_text
        )

        missing_box.config(
            state=tk.DISABLED
        )

        missing_box.pack(
            fill=tk.X,
            pady=(2, 6)
        )

        # ----------------------------------------------------
        # SENSITIVE ELEMENTS
        # ----------------------------------------------------

        tk.Label(
            model_frame,
            text="🔐 Sensitive Elements",
            font=("Arial", 9, "bold"),
            fg="#1f4e79",
            bg="white"
        ).pack(
            anchor=tk.W
        )

        sensitive_text = "\n".join(
            f"• {item}"
            for item in result["sensitive_elements"]
        )

        if not sensitive_text:
            sensitive_text = "None identified."

        sensitive_box = tk.Text(
            model_frame,
            height=max(
                2,
                min(
                    6,
                    len(result["sensitive_elements"]) + 1
                )
            ),
            font=("Arial", 9),
            wrap=tk.WORD,
            bg="#f8f9fa",
            relief=tk.SOLID,
            bd=1
        )

        sensitive_box.insert(
            tk.END,
            sensitive_text
        )

        sensitive_box.config(
            state=tk.DISABLED
        )

        sensitive_box.pack(
            fill=tk.X,
            pady=(2, 6)
        )

        # ----------------------------------------------------
        # RED FLAGS
        # ----------------------------------------------------

        tk.Label(
            model_frame,
            text="🚨 Red Flags",
            font=("Arial", 9, "bold"),
            fg="#b22222",
            bg="white"
        ).pack(
            anchor=tk.W
        )

        red_flags_text = "\n".join(
            f"• {flag}"
            for flag in result["red_flags"]
        )

        if not red_flags_text:
            red_flags_text = "None detected."

        red_flags_box = tk.Text(
            model_frame,
            height=max(
                2,
                min(
                    6,
                    len(result["red_flags"]) + 1
                )
            ),
            font=("Arial", 9),
            wrap=tk.WORD,
            bg="#fff8f8",
            relief=tk.SOLID,
            bd=1
        )

        red_flags_box.insert(
            tk.END,
            red_flags_text
        )

        red_flags_box.config(
            state=tk.DISABLED
        )

        red_flags_box.pack(
            fill=tk.X,
            pady=(2, 6)
        )

    # ========================================================
    # RESET SCROLL POSITION
    # ========================================================

    output_canvas.update_idletasks()

    output_canvas.configure(
        scrollregion=output_canvas.bbox("all")
    )

    output_canvas.yview_moveto(0)


# ============================================================
# MAIN ANALYSIS
# ============================================================

def handle_analysis():

    raw_text = text_input.get(
        "1.0",
        tk.END
    ).strip()

    if not raw_text:

        messagebox.showwarning(
            "Input Missing",
            "Please paste text or upload a consent document."
        )

        return

    selected_models = []

    if choice_sonnet.get():

        selected_models.append(
            (
                "Claude 5 Sonnet",
                MODEL_CONFIG["Claude 5 Sonnet"]["id"]
            )
        )

    if choice_haiku.get():

        selected_models.append(
            (
                "Claude 4.5 Haiku",
                MODEL_CONFIG["Claude 4.5 Haiku"]["id"]
            )
        )

    if choice_opus.get():

        selected_models.append(
            (
                "Claude 4.8 Opus",
                MODEL_CONFIG["Claude 4.8 Opus"]["id"]
            )
        )

    if not selected_models:

        messagebox.showwarning(
            "Selection Missing",
            "Select at least one model."
        )

        return

    # Clear previous output
    for widget in frame_output_container.winfo_children():
        widget.destroy()

    status_label.config(
        text="🔐 Anonymizing document...",
        fg="orange"
    )

    root.update_idletasks()

    # ========================================================
    # PII SCRUB
    # ========================================================

    anonymized_text = clean_pii_data(
        raw_text
    )

    # ========================================================
    # RUN MODELS
    # ========================================================

    results = []

    for model_name, model_id in selected_models:

        status_label.config(
            text=f"🤖 Running {model_name}...",
            fg="orange"
        )

        root.update_idletasks()

        result = analyze_model(
            model_name,
            model_id,
            anonymized_text
        )

        results.append(result)

    # ========================================================
    # COMPARISON
    # ========================================================

    results = calculate_comparison(
        results
    )

    display_comparison_table(
        results
    )

    status_label.config(
        text="✅ Comparative Analysis Complete!",
        fg="green"
    )


# ============================================================
# GUI
# ============================================================

root = tk.Tk()

root.title(
    "AI Consent Explainer Engine - Model Comparison"
)

root.geometry(
    "1100x750"
)

root.minsize(
    950,
    650
)


# ============================================================
# MODEL CHECKLIST
# ============================================================

frame_top = tk.Frame(
    root,
    pady=10,
    bg="#f1f1f1",
    bd=1,
    relief=tk.GROOVE
)

frame_top.pack(
    fill=tk.X,
    padx=15,
    pady=10
)

tk.Label(
    frame_top,
    text="Checklist - Select Models to Compare:",
    font=("Arial", 10, "bold"),
    bg="#f1f1f1"
).pack(
    side=tk.LEFT,
    padx=(10, 20)
)


choice_sonnet = tk.IntVar(value=1)
choice_haiku = tk.IntVar(value=1)
choice_opus = tk.IntVar(value=1)


tk.Checkbutton(
    frame_top,
    text="Claude 5 Sonnet",
    variable=choice_sonnet,
    font=("Arial", 9),
    bg="#f1f1f1"
).pack(
    side=tk.LEFT,
    padx=15
)


tk.Checkbutton(
    frame_top,
    text="Claude 4.5 Haiku",
    variable=choice_haiku,
    font=("Arial", 9),
    bg="#f1f1f1"
).pack(
    side=tk.LEFT,
    padx=15
)


tk.Checkbutton(
    frame_top,
    text="Claude 4.8 Opus",
    variable=choice_opus,
    font=("Arial", 9),
    bg="#f1f1f1"
).pack(
    side=tk.LEFT,
    padx=15
)


# ============================================================
# INPUT HEADER
# ============================================================

frame_input_header = tk.Frame(
    root
)

frame_input_header.pack(
    fill=tk.X,
    padx=15,
    pady=(5, 2)
)


tk.Label(
    frame_input_header,
    text="Paste Consent Clause or Upload Document:",
    font=("Arial", 10, "bold")
).pack(
    side=tk.LEFT
)


tk.Button(
    frame_input_header,
    text="📁 Upload Document (.pdf / .txt)",
    command=browse_file,
    bg="#5cb85c",
    fg="white",
    font=("Arial", 9, "bold"),
    padx=10
).pack(
    side=tk.RIGHT
)


# ============================================================
# INPUT BOX
# ============================================================

# ============================================================
# SCROLLABLE INPUT AREA
# ============================================================

input_frame = tk.Frame(
    root,
    padx=15
)

input_frame.pack(
    fill=tk.X
)

text_input = tk.Text(
    input_frame,
    height=8,
    font=("Arial", 10),
    wrap=tk.WORD
)

input_scrollbar = ttk.Scrollbar(
    input_frame,
    orient=tk.VERTICAL,
    command=text_input.yview
)

text_input.configure(
    yscrollcommand=input_scrollbar.set
)

text_input.pack(
    side=tk.LEFT,
    fill=tk.X,
    expand=True
)

input_scrollbar.pack(
    side=tk.RIGHT,
    fill=tk.Y
)


# ============================================================
# CONTROL BAR
# ============================================================

frame_controls = tk.Frame(
    root,
    pady=10
)

frame_controls.pack(
    fill=tk.X,
    padx=15
)


tk.Button(
    frame_controls,
    text="Run Comparative Analysis",
    command=handle_analysis,
    bg="#0275d8",
    fg="white",
    font=("Arial", 10, "bold"),
    padx=25
).pack(
    side=tk.LEFT
)


status_label = tk.Label(
    frame_controls,
    text="Ready",
    font=("Arial", 10, "italic"),
    fg="gray"
)

status_label.pack(
    side=tk.LEFT,
    padx=15
)


# ============================================================
# OUTPUT
# ============================================================

frame_output_container = tk.Frame(
    root
)

frame_output_container.pack(
    fill=tk.BOTH,
    expand=True,
    padx=15,
    pady=(5, 15)
)


# ============================================================
# START APPLICATION
# ============================================================

root.mainloop()
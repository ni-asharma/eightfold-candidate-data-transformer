import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def main() -> None:
    os.makedirs("outputs", exist_ok=True)
    pdf_path = "outputs/design_document.pdf"
    
    # 1. Page Template Setup (Margins set to 36pt / 0.5 inch for maximum printable area)
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # 2. Typography & Casing Styles (Color scheme: Navy, Slate, and Charcoal)
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"), # Slate 900
        spaceAfter=2
    )
    
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"), # Slate 600
        spaceAfter=8
    )
    
    h1_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1E3A8A"), # Deep Blue
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        "SectionBody",
        parent=styles["Normal"],
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#334155"), # Slate 700
        spaceAfter=4
    )
    
    # 3. Document Header Block
    story.append(Paragraph("System Architecture: Multi-Source Candidate Data Transformer", title_style))
    story.append(Paragraph("<b>Author:</b> Senior Staff Backend Engineer, Eightfold AI &nbsp;&nbsp;|&nbsp;&nbsp; <b>Status:</b> Approved &nbsp;&nbsp;|&nbsp;&nbsp; <b>Target Page Budget:</b> 1 Page", subtitle_style))
    
    # Thin divider line
    line_table = Table([[""]], colWidths=[540])
    line_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 4))
    
    # 4. Column Content Assembly (Decoupled 2-Column layout)
    col1_content = [
        Paragraph("1. Ingestion Pipeline & Architecture", h1_style),
        Paragraph(
            "The ingestion pipeline is designed around a decoupled, stage-based flow: "
            "Ingestion Parsers &rarr; Field Normalizers &rarr; Schema Validation &rarr; "
            "Entity Resolution &rarr; Conflict Resolution &rarr; Configurable Projection. "
            "Each module operates as an isolated worker block. System resiliency is handled "
            "at the field level; malformed CSV entries, missing fields, or empty PDFs do not "
            "crash the pipeline, but trigger null-recovery fallbacks and audit warnings.",
            body_style
        ),
        
        Paragraph("2. Canonical Candidate Schema", h1_style),
        Paragraph(
            "Rather than storing only the unified scalar values, the Canonical profile "
            "encapsulates each attribute in a typed <i>MergedField[T]</i> schema. "
            "This model explicitly logs metadata for every decision: winning source, "
            "raw competing values, normalized values, applied strategy, confidence score, "
            "and a detailed reason. This guarantees data provenance and complete "
            "system explainability out-of-the-box.",
            body_style
        ),
        
        Paragraph("3. Conflict Resolution Engine", h1_style),
        Paragraph(
            "Conflict resolution is resolved using a deterministic priority queue:<br/>"
            "• <b>Exact match:</b> Identical values across all sources (agreement boost).<br/>"
            "• <b>Normalized match:</b> Match after cleanup (e.g. C++ vs. c plus plus).<br/>"
            "• <b>Source Reliability:</b> Highest weight source wins (CSV > ATS > Resume > Notes).<br/>"
            "• <b>Completeness:</b> Longer strings or larger lists win on tie-breaker.<br/>"
            "• <b>Timeline Date:</b> Chosen based on the latest work experience history end date.<br/>"
            "• <b>Fallback:</b> Alphabetical fallback + list-union for skills/URLs.",
            body_style
        ),
    ]
    
    col2_content = [
        Paragraph("4. Confidence Score Model", h1_style),
        Paragraph(
            "Field confidence is calculated using the formula:<br/>"
            "<i>C = min(R_s * N_s * V_s * A, 1.0)</i><br/>"
            "Where components represent:<br/>"
            "• <b>R_s (Source Weight):</b> Loaded from dynamic configuration "
            "(default weights: CSV=0.95, ATS=0.90, Resume=0.80, Notes=0.60).<br/>"
            "• <b>N_s (Normalization Success):</b> 1.0 on success, 0.7 on fallback/failure.<br/>"
            "• <b>V_s (Validation Success):</b> 1.0 on passed Pydantic rules, 0.5 on failure.<br/>"
            "• <b>A (Agreement Multiplier):</b> 1.0 + 0.05 * (k - 1) for k agreeing sources.",
            body_style
        ),
        
        Paragraph("5. Configurable Projection Layer", h1_style),
        Paragraph(
            "The canonical record is treated as an immutable ledger. Target representations "
            "are generated on-the-fly using a JSON config file. Users can customize "
            "field selections, map fields (e.g. first_name &rarr; fname), apply post-normalizers "
            "(e.g. lowercase emails), choose missing-value policies (fill_null, ignore, "
            "default_value), and toggle confidence scores and provenance logs without "
            "changing the core engine code.",
            body_style
        ),
        
        Paragraph("6. Trade-offs & Edge Cases", h1_style),
        Paragraph(
            "• <b>Trade-off (Complexity vs. Performance):</b> Running connected-components "
            "graph groupings for entity resolution increases CPU time but is necessary "
            "to prevent candidate duplicate clusters.<br/>"
            "• <b>Edge Cases (Multiple Employments):</b> Grouping work experience solely by company "
            "risks merging disjoint employments (e.g., worked at Google in 2020, and again in 2024). "
            "Our engine checks date-interval overlaps to ensure they are merged only "
            "if their timelines intersect; otherwise, they remain separate experiences.",
            body_style
        ),
    ]
    
    # 5. Two-column grid table (540pt width divided into 260pt columns with a 20pt gap)
    col_table = Table([[col1_content, "", col2_content]], colWidths=[260, 20, 260])
    col_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(col_table)
    
    # 6. Page Footer Section
    story.append(Spacer(1, 12))
    footer_table = Table([["Confidential - Eightfold AI Data Ingestion Team. All rights reserved."]], colWidths=[540])
    footer_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#94A3B8")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(footer_table)
    
    doc.build(story)
    print(f"Generated design document PDF at {pdf_path}")

if __name__ == "__main__":
    main()

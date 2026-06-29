import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def main() -> None:
    os.makedirs("sample_inputs", exist_ok=True)
    pdf_path = "sample_inputs/resume.pdf"
    
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
    
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        spaceAfter=10
    )
    
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=6
    )
    
    story.append(Paragraph("Name: John Doe", title_style))
    story.append(Paragraph("Email: john.doe@example.com", body_style))
    story.append(Paragraph("Phone: (415) 555-0100", body_style))
    story.append(Paragraph("Location: San Francisco, CA", body_style))
    story.append(Paragraph("Urls: https://github.com/johndoe, https://linkedin.com/in/johndoe", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Skills: python, cpp, javascript, docker, kubernetes", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Company: Google", body_style))
    story.append(Paragraph("Title: Software Engineer", body_style))
    story.append(Paragraph("Dates: 2022-01 to 2023-12", body_style))
    story.append(Paragraph("Description: Worked on distributed backend storage systems and improved database access latency.", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("School: Stanford University", body_style))
    story.append(Paragraph("Degree: Bachelor of Science", body_style))
    story.append(Paragraph("Field: Computer Science", body_style))
    story.append(Paragraph("Dates: 2018-09 to 2022-06", body_style))
    
    doc.build(story)
    print(f"Generated sample PDF resume at {pdf_path}")

if __name__ == "__main__":
    main()

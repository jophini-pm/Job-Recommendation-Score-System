# Job Recommendation Score System

A Flask-based application that analyzes candidate resumes and compares them to job descriptions, producing match scores across Experience, Skills, and Education categories.

## Features

- **Resume Parsing**: Supports PDF, DOCX, and TXT formats
- **Semantic Matching**: Uses Sentence-BERT for intelligent similarity detection (when available)
- **Multi-category Scoring**: Experience (30%), Skills (50%), Education (20%)
- **Web Interface**: Simple upload and results visualization
- **REST API**: JSON endpoint for programmatic access
- **Local Processing**: No external APIs required

## Requirements

- Python 3.7+
- pip package manager

## Quick Start

### Installation

1. **Create project folder**
```bash
mkdir job-recommendation-system
cd job-recommendation-system
```

2. **Save the files**
   - Save `app.py` (main Python file)
   - Save `requirements.txt` (dependencies)
   - Save this `README.md`

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Run the application**
```bash
python app.py
```

5. **Access the application**
   - Web Interface: http://localhost:5000
   - API Endpoint: POST http://localhost:5000/match

## Usage

### Web Interface

1. Open http://localhost:5000 in your browser
2. Upload a resume file (PDF, DOCX, or TXT)
3. Paste the job description in the text area
4. Click "Calculate Match Score"
5. View detailed results with score breakdown

### API Usage

```bash
curl -X POST http://localhost:5000/match \
  -F "resume=@path/to/resume.pdf" \
  -F "job_description=Your job description text here"
```

### Sample Input/Output

**Sample Resume (resume.txt):**
```
Name: Rahul Sharma
Experience:
- 6 years at Flipkart as a UI/UX Designer
- Conducted A/B testing, created wireframes, user research

Skills:
- Figma, Adobe XD, HTML/CSS, Prototyping, UX Research

Education:
- B.Des from NID Ahmedabad, 2015
```

**Sample Job Description:**
```
Role: Senior UI/UX Designer 
Required: 
- 5+ years experience 
- Prototyping, Wireframing, Figma, Adobe XD 
- Bachelor's or Master's in Design or HCI
```

**Expected Output:**
```json
{
  "candidate_name": "Rahul Sharma",
  "job_title": "Senior UI/UX Designer",
  "match_scores": {
    "experience_match": 90,
    "skills_match": 77,
    "education_match": 92,
    "overall_score": 85
  }
}
```

## Architecture

### Core Components

1. **ResumeParser**: Extracts structured data from resume files
2. **JobMatcher**: Analyzes job requirements and calculates match scores
3. **Flask App**: Web interface and API endpoints

### Scoring Algorithm

- **Experience Match**: Compares years of experience and domain relevance
- **Skills Match**: Uses semantic similarity + keyword matching (when available)
- **Education Match**: Matches degree types and fields of study
- **Overall Score**: Weighted average (Skills 50%, Experience 30%, Education 20%)

### Semantic Matching

The application attempts to use `sentence-transformers` with the `all-MiniLM-L6-v2` model for semantic similarity. If not available, it falls back to keyword-based matching.

## File Structure

```
job-recommendation-system/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── README.md          # This file
├── uploads/           # Temporary file storage (created automatically)
└── sample_files/      # Sample test files (optional)
```

## API Endpoints

### POST /match
Analyzes resume against job description and returns match scores.

**Parameters:**
- `resume` (file): Resume file (PDF, DOCX, or TXT)
- `job_description` (text): Job description text

**Response:**
```json
{
  "candidate_name": "string",
  "job_title": "string", 
  "match_scores": {
    "experience_match": 0-100,
    "skills_match": 0-100,
    "education_match": 0-100,
    "overall_score": 0-100
  }
}
```

### GET /health
Health check endpoint.

## Troubleshooting

### Common Issues

1. **"ModuleNotFoundError"**: Run `pip install -r requirements.txt`
2. **"Permission denied" on file upload**: Check file permissions and upload folder
3. **Low accuracy**: Add more specific keywords to resume/job description
4. **Semantic matching disabled**: This is normal if sentence-transformers fails to load

### Python Version Compatibility

- **Tested with**: Python 3.7.9
- **Dependencies**: Compatible versions specified in requirements.txt
- **Fallback**: Works with keyword matching only if semantic libraries fail

### Performance Notes

- First semantic model load may take 1-2 minutes
- PDF parsing depends on file quality
- Large files (>10MB) may timeout

## Testing

Create test files and try different scenarios:

1. **Different file formats**: Test PDF, DOCX, TXT resumes
2. **Various job descriptions**: Different industries and roles  
3. **Edge cases**: Missing sections, unusual formatting
4. **API testing**: Use curl or Postman for API endpoints

## Competition Submission

This implementation includes all required features:

- Flask-based microservice
- Resume parsing (PDF, DOCX, TXT)
- Job description analysis
- Multi-category scoring with weights
- Semantic matching (bonus feature)
- Web interface (bonus feature)
- Local execution (no external APIs)
- Structured JSON output
- Clean, modular code
- Complete documentation

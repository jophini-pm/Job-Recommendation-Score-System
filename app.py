import os
import re
import json
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import PyPDF2
import docx
import numpy as np
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import warnings
warnings.filterwarnings('ignore')

# Try to import sentence transformers (for semantic matching)
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Sentence transformers not available. Using keyword matching only.")

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
except:
    pass

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load semantic model (using a lightweight model for local execution)
if TRANSFORMERS_AVAILABLE:
    try:
        semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
        SEMANTIC_MATCHING = True
        print("Semantic matching enabled with sentence-transformers")
    except Exception as e:
        semantic_model = None
        SEMANTIC_MATCHING = False
        print(f"Could not load semantic model: {e}")
else:
    semantic_model = None
    SEMANTIC_MATCHING = False
    print("Semantic matching disabled - using keyword matching only")

class ResumeParser:
    def __init__(self):
        self.stop_words = set(stopwords.words('english')) if nltk.data.find('corpora/stopwords') else set()
    
    def extract_text_from_pdf(self, file_path):
        """Extract text from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
        except Exception as e:
            print(f"Error reading PDF: {e}")
            return ""
    
    def extract_text_from_docx(self, file_path):
        """Extract text from DOCX file"""
        try:
            doc = docx.Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            print(f"Error reading DOCX: {e}")
            return ""
    
    def extract_text_from_txt(self, file_path):
        """Extract text from TXT file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            print(f"Error reading TXT: {e}")
            return ""
    
    def extract_text_from_file(self, file_path):
        """Extract text based on file extension"""
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        if ext == '.pdf':
            return self.extract_text_from_pdf(file_path)
        elif ext == '.docx':
            return self.extract_text_from_docx(file_path)
        elif ext == '.txt':
            return self.extract_text_from_txt(file_path)
        else:
            return ""
    
    def extract_name(self, text):
        """Extract candidate name from resume text"""
        lines = text.strip().split('\n')
        # Look for name patterns in first few lines
        for line in lines[:5]:
            line = line.strip()
            if line and not any(keyword in line.lower() for keyword in ['email', 'phone', 'address', 'linkedin']):
                # Check if line looks like a name (contains letters and possibly spaces)
                if re.match(r'^[A-Za-z\s\.]+$', line) and len(line.split()) <= 4:
                    return line.strip()
        
        # Fallback: look for "Name:" pattern
        name_match = re.search(r'Name\s*:\s*(.+)', text, re.IGNORECASE)
        if name_match:
            return name_match.group(1).strip()
        
        return "Unknown Candidate"
    
    def extract_section(self, text, section_keywords, end_keywords=None):
        """Extract content from a specific section"""
        text_lower = text.lower()
        section_content = []
        
        # Find section start
        start_pos = -1
        for keyword in section_keywords:
            pos = text_lower.find(keyword.lower())
            if pos != -1 and (start_pos == -1 or pos < start_pos):
                start_pos = pos
        
        if start_pos == -1:
            return []
        
        # Find section end
        end_pos = len(text)
        if end_keywords:
            for keyword in end_keywords:
                pos = text_lower.find(keyword.lower(), start_pos + 1)
                if pos != -1 and pos < end_pos:
                    end_pos = pos
        
        section_text = text[start_pos:end_pos]
        
        # Clean and extract items
        lines = section_text.split('\n')
        for line in lines[1:]:  # Skip the header line
            line = line.strip()
            if line and not any(kw in line.lower() for kw in section_keywords + (end_keywords or [])):
                # Remove bullet points and clean
                line = re.sub(r'^[\-\•\*\+\s]+', '', line)
                if line:
                    section_content.append(line)
        
        return section_content
    
    def parse_resume(self, text):
        """Parse resume and extract structured information"""
        result = {
            'name': self.extract_name(text),
            'experience': [],
            'skills': [],
            'education': []
        }
        
        # Extract experience
        exp_keywords = ['experience', 'work experience', 'employment', 'work history']
        exp_end_keywords = ['education', 'skills', 'projects', 'achievements']
        result['experience'] = self.extract_section(text, exp_keywords, exp_end_keywords)
        
        # Extract skills
        skill_keywords = ['skills', 'technical skills', 'core competencies', 'expertise']
        skill_end_keywords = ['experience', 'education', 'projects', 'achievements']
        result['skills'] = self.extract_section(text, skill_keywords, skill_end_keywords)
        
        # Extract education
        edu_keywords = ['education', 'academic background', 'qualifications']
        edu_end_keywords = ['experience', 'skills', 'projects', 'achievements']
        result['education'] = self.extract_section(text, edu_keywords, edu_end_keywords)
        
        return result

class JobMatcher:
    def __init__(self, semantic_model=None):
        self.semantic_model = semantic_model
    
    def extract_job_requirements(self, jd_text):
        """Extract requirements from job description"""
        result = {
            'title': 'Job Position',
            'required_experience': [],
            'required_skills': [],
            'required_education': []
        }
        
        # Extract job title
        title_match = re.search(r'(role|position|title)\s*:\s*(.+)', jd_text, re.IGNORECASE)
        if title_match:
            result['title'] = title_match.group(2).strip()
        
        # Extract experience requirements
        exp_patterns = [
            r'(\d+)\+?\s*years?\s*(of\s*)?experience',
            r'experience\s*:\s*(.+)',
            r'minimum\s*(\d+)\s*years?'
        ]
        
        for pattern in exp_patterns:
            matches = re.findall(pattern, jd_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = ' '.join(str(m) for m in match if m)
                result['required_experience'].append(match.strip())
        
        # Extract skills and tools
        skills_section = re.search(r'(skills|required|tools|technologies)\s*:(.+?)(?=\n\n|\n[A-Z]|$)', 
                                 jd_text, re.IGNORECASE | re.DOTALL)
        if skills_section:
            skills_text = skills_section.group(2)
            # Split by common separators
            skills = re.split(r'[,;\n\-\•\*]+', skills_text)
            result['required_skills'] = [skill.strip() for skill in skills if skill.strip()]
        
        # Extract education requirements
        edu_patterns = [
            r'(bachelor|master|phd|degree)\s*.*?(in\s*.+?)(?=[,\n\.]|$)',
            r'education\s*:\s*(.+)'
        ]
        
        for pattern in edu_patterns:
            matches = re.findall(pattern, jd_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = ' '.join(str(m) for m in match if m)
                result['required_education'].append(match.strip())
        
        return result
    
    def semantic_similarity(self, text1_list, text2_list):
        """Calculate semantic similarity between two text lists"""
        if not TRANSFORMERS_AVAILABLE or not self.semantic_model or not text1_list or not text2_list:
            return 0.0
        
        try:
            # Combine lists into single strings
            text1 = ' '.join(text1_list)
            text2 = ' '.join(text2_list)
            
            # Get embeddings
            embeddings1 = self.semantic_model.encode([text1])
            embeddings2 = self.semantic_model.encode([text2])
            
            # Calculate cosine similarity
            similarity = cosine_similarity(embeddings1, embeddings2)[0][0]
            return max(0, similarity * 100)  # Convert to percentage
        except Exception as e:
            print(f"Semantic similarity calculation failed: {e}")
            return 0.0
    
    def keyword_similarity(self, resume_items, required_items):
        """Calculate keyword-based similarity"""
        if not resume_items or not required_items:
            return 0.0
        
        resume_text = ' '.join(resume_items).lower()
        required_text = ' '.join(required_items).lower()
        
        # Extract keywords (remove common words)
        resume_words = set(re.findall(r'\w+', resume_text))
        required_words = set(re.findall(r'\w+', required_text))
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        resume_words -= stop_words
        required_words -= stop_words
        
        if not required_words:
            return 0.0
        
        # Calculate overlap
        overlap = len(resume_words.intersection(required_words))
        similarity = (overlap / len(required_words)) * 100
        
        return min(100, similarity)
    
    def calculate_experience_match(self, resume_exp, required_exp):
        """Calculate experience match score"""
        if not resume_exp:
            return 0.0
        
        # Extract years from resume
        resume_years = []
        for exp in resume_exp:
            year_matches = re.findall(r'(\d+)\s*years?', exp, re.IGNORECASE)
            resume_years.extend([int(y) for y in year_matches])
        
        total_resume_years = sum(resume_years) if resume_years else 0
        
        # Extract required years
        required_years = 0
        for req in required_exp:
            year_matches = re.findall(r'(\d+)', str(req))
            if year_matches:
                required_years = max(required_years, int(year_matches[0]))
        
        if required_years == 0:
            return 50.0  # Default score if no specific requirement
        
        # Calculate match
        if total_resume_years >= required_years:
            return min(100, (total_resume_years / required_years) * 85)
        else:
            return (total_resume_years / required_years) * 70
    
    def calculate_skills_match(self, resume_skills, required_skills):
        """Calculate skills match score"""
        if not resume_skills or not required_skills:
            return 0.0
        
        # Use semantic matching if available, otherwise use keyword matching
        if SEMANTIC_MATCHING:
            semantic_score = self.semantic_similarity(resume_skills, required_skills)
            keyword_score = self.keyword_similarity(resume_skills, required_skills)
            return (semantic_score * 0.7 + keyword_score * 0.3)
        else:
            return self.keyword_similarity(resume_skills, required_skills)
    
    def calculate_education_match(self, resume_education, required_education):
        """Calculate education match score"""
        if not resume_education:
            return 0.0
        
        if not required_education:
            return 50.0  # Default score if no specific requirement
        
        # Use semantic matching if available, otherwise use keyword matching
        if SEMANTIC_MATCHING:
            semantic_score = self.semantic_similarity(resume_education, required_education)
            keyword_score = self.keyword_similarity(resume_education, required_education)
            return (semantic_score * 0.6 + keyword_score * 0.4)
        else:
            return self.keyword_similarity(resume_education, required_education)
    
    def calculate_overall_score(self, exp_score, skills_score, edu_score):
        """Calculate weighted overall score"""
        weights = {
            'skills': 0.5,
            'experience': 0.3,
            'education': 0.2
        }
        
        overall = (skills_score * weights['skills'] + 
                  exp_score * weights['experience'] + 
                  edu_score * weights['education'])
        
        return round(overall, 0)

# Initialize components
resume_parser = ResumeParser()
job_matcher = JobMatcher(semantic_model)

@app.route('/')
def index():
    """Main page with upload form"""
    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Job Recommendation Score System</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; text-align: center; margin-bottom: 30px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; font-weight: bold; color: #555; }
            input[type="file"], textarea { width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; font-size: 14px; }
            textarea { height: 120px; resize: vertical; }
            .submit-btn { background-color: #007bff; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin-top: 20px; }
            .submit-btn:hover { background-color: #0056b3; }
            .info { background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            .semantic-status { text-align: center; margin-bottom: 20px; padding: 10px; border-radius: 5px; }
            .semantic-enabled { background-color: #d4edda; color: #155724; }
            .semantic-disabled { background-color: #f8d7da; color: #721c24; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Job Recommendation Score System</h1>
            
            <div class="semantic-status {{ 'semantic-enabled' if semantic_matching else 'semantic-disabled' }}">
                <strong>Semantic Matching: {{ 'Enabled' if semantic_matching else 'Disabled (Using keyword matching only)' }}</strong>
            </div>
            
            <div class="info">
                <strong>Instructions:</strong>
                <ul>
                    <li>Upload a resume in PDF, DOCX, or TXT format</li>
                    <li>Paste or type the job description in the text area below</li>
                    <li>Click "Calculate Match Score" to get detailed matching results</li>
                    <li>Supported resume formats: .pdf, .docx, .txt</li>
                </ul>
            </div>
            
            <form action="/match" method="post" enctype="multipart/form-data">
                <div class="form-group">
                    <label for="resume">Upload Resume:</label>
                    <input type="file" id="resume" name="resume" accept=".pdf,.docx,.txt" required>
                </div>
                
                <div class="form-group">
                    <label for="job_description">Job Description:</label>
                    <textarea id="job_description" name="job_description" placeholder="Paste the job description here..." required></textarea>
                </div>
                
                <button type="submit" class="submit-btn">Calculate Match Score</button>
            </form>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_template, semantic_matching=SEMANTIC_MATCHING)

@app.route('/match', methods=['POST'])
def match_resume():
    """Main matching endpoint"""
    try:
        # Check if resume file is provided
        if 'resume' not in request.files:
            return jsonify({'error': 'No resume file provided'}), 400
        
        file = request.files['resume']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get job description
        job_description = request.form.get('job_description', '').strip()
        if not job_description:
            return jsonify({'error': 'Job description is required'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            # Extract text from resume
            resume_text = resume_parser.extract_text_from_file(file_path)
            if not resume_text.strip():
                return jsonify({'error': 'Could not extract text from resume file'}), 400
            
            # Parse resume
            parsed_resume = resume_parser.parse_resume(resume_text)
            
            # Parse job description
            job_requirements = job_matcher.extract_job_requirements(job_description)
            
            # Calculate match scores
            exp_score = job_matcher.calculate_experience_match(
                parsed_resume['experience'], 
                job_requirements['required_experience']
            )
            
            skills_score = job_matcher.calculate_skills_match(
                parsed_resume['skills'], 
                job_requirements['required_skills']
            )
            
            edu_score = job_matcher.calculate_education_match(
                parsed_resume['education'], 
                job_requirements['required_education']
            )
            
            overall_score = job_matcher.calculate_overall_score(exp_score, skills_score, edu_score)
            
            # Prepare response
            result = {
                'candidate_name': parsed_resume['name'],
                'job_title': job_requirements['title'],
                'match_scores': {
                    'experience_match': int(exp_score),
                    'skills_match': int(skills_score),
                    'education_match': int(edu_score),
                    'overall_score': int(overall_score)
                },
                'details': {
                    'parsed_resume': parsed_resume,
                    'job_requirements': job_requirements,
                    'semantic_matching_used': SEMANTIC_MATCHING
                }
            }
            
            # Return JSON if requested via API, otherwise render HTML
            if request.headers.get('Content-Type') == 'application/json' or 'application/json' in request.headers.get('Accept', ''):
                return jsonify(result)
            else:
                return render_result_page(result)
        
        finally:
            # Clean up uploaded file
            try:
                os.remove(file_path)
            except:
                pass
    
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

def render_result_page(result):
    """Render results page with detailed breakdown"""
    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Match Results - Job Recommendation System</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
            .container { max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1, h2 { color: #333; }
            .score-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }
            .score-card { background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #007bff; }
            .score-value { font-size: 36px; font-weight: bold; color: #007bff; }
            .score-label { font-size: 14px; color: #666; margin-top: 5px; }
            .overall-score { background: linear-gradient(135deg, #007bff, #0056b3); color: white; }
            .details { background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }
            .back-btn { background-color: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 20px; }
            .back-btn:hover { background-color: #545b62; }
            ul { margin: 10px 0; }
            li { margin: 5px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Job Match Results</h1>
            
            <h2>{{ result.candidate_name }} → {{ result.job_title }}</h2>
            
            <div class="score-grid">
                <div class="score-card overall-score">
                    <div class="score-value">{{ result.match_scores.overall_score }}%</div>
                    <div class="score-label">Overall Match</div>
                </div>
                <div class="score-card">
                    <div class="score-value">{{ result.match_scores.skills_match }}%</div>
                    <div class="score-label">Skills Match (50% weight)</div>
                </div>
                <div class="score-card">
                    <div class="score-value">{{ result.match_scores.experience_match }}%</div>
                    <div class="score-label">Experience Match (30% weight)</div>
                </div>
                <div class="score-card">
                    <div class="score-value">{{ result.match_scores.education_match }}%</div>
                    <div class="score-label">Education Match (20% weight)</div>
                </div>
            </div>
            
            <div class="details">
                <h3>Resume Analysis</h3>
                <p><strong>Skills Found:</strong></p>
                <ul>
                    {% for skill in result.details.parsed_resume.skills %}
                    <li>{{ skill }}</li>
                    {% endfor %}
                </ul>
                
                <p><strong>Experience Found:</strong></p>
                <ul>
                    {% for exp in result.details.parsed_resume.experience %}
                    <li>{{ exp }}</li>
                    {% endfor %}
                </ul>
                
                <p><strong>Education Found:</strong></p>
                <ul>
                    {% for edu in result.details.parsed_resume.education %}
                    <li>{{ edu }}</li>
                    {% endfor %}
                </ul>
            </div>
            
            <div class="details">
                <h3>Job Requirements</h3>
                <p><strong>Required Skills:</strong></p>
                <ul>
                    {% for skill in result.details.job_requirements.required_skills %}
                    <li>{{ skill }}</li>
                    {% endfor %}
                </ul>
                
                <p><strong>Required Experience:</strong></p>
                <ul>
                    {% for exp in result.details.job_requirements.required_experience %}
                    <li>{{ exp }}</li>
                    {% endfor %}
                </ul>
                
                <p><strong>Required Education:</strong></p>
                <ul>
                    {% for edu in result.details.job_requirements.required_education %}
                    <li>{{ edu }}</li>
                    {% endfor %}
                </ul>
            </div>
            
            <div class="details">
                <p><strong>Matching Method:</strong> {{ 'Semantic + Keyword Matching' if result.details.semantic_matching_used else 'Keyword Matching Only' }}</p>
            </div>
            
            <a href="/" class="back-btn">← Back to Upload</a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_template, result=result)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'semantic_matching': SEMANTIC_MATCHING,
        'version': '1.0.0'
    })

if __name__ == '__main__':
    print(f"Job Recommendation Score System")
    print(f"Semantic matching: {'Enabled' if SEMANTIC_MATCHING else 'Disabled'}")
    print(f"Starting server on http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)


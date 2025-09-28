from flask import Flask, request, jsonify, session
from flask_cors import CORS
import pymongo
import os
import json
import bcrypt
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "educompanion-secret-key")
CORS(app)

# MongoDB connection
try:
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    client = pymongo.MongoClient(mongo_uri)
    db = client["educompanion"]
    users_collection = db["users"]
    user_files_collection = db["user_files"]
    print("Connected to MongoDB successfully!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")

# Gemini API setup
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    print("Gemini API configured successfully!")
except Exception as e:
    print(f"Error configuring Gemini API: {e}")

# Routes
@app.route('/')
def home():
    return "EduCompanion API is running!"

# User Authentication
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        grade = data.get('grade', 'Not specified')
        
        # Check if user already exists
        if users_collection.find_one({"username": username}):
            return jsonify({"success": False, "message": "Username already exists"}), 400
        
        if users_collection.find_one({"email": email}):
            return jsonify({"success": False, "message": "Email already exists"}), 400
        
        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Create user
        user = {
            "username": username,
            "password": hashed_password,
            "email": email,
            "grade": grade,
            "created_at": pymongo.datetime.datetime.now()
        }
        
        users_collection.insert_one(user)
        
        # Create user's initial file
        create_user_file(username)
        
        return jsonify({"success": True, "message": "User registered successfully"}), 201
    
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        # Find user
        user = users_collection.find_one({"username": username})
        
        if not user:
            return jsonify({"success": False, "message": "Invalid username or password"}), 401
        
        # Check password
        if bcrypt.checkpw(password.encode('utf-8'), user['password']):
            # Set session
            session['user_id'] = str(user['_id'])
            session['username'] = username
            
            # Create user file if it doesn't exist
            create_user_file(username)
            
            return jsonify({
                "success": True, 
                "message": "Login successful",
                "user": {
                    "username": username,
                    "email": user.get('email'),
                    "grade": user.get('grade')
                }
            }), 200
        else:
            return jsonify({"success": False, "message": "Invalid username or password"}), 401
    
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

# User file creation
def create_user_file(username):
    """Create a file for the user in MongoDB if it doesn't exist"""
    if not user_files_collection.find_one({"username": username}):
        user_file = {
            "username": username,
            "content": "Welcome to EduCompanion!",
            "created_at": pymongo.datetime.datetime.now(),
            "updated_at": pymongo.datetime.datetime.now()
        }
        user_files_collection.insert_one(user_file)
        return True
    return False

@app.route('/api/user/file', methods=['GET'])
def get_user_file():
    if 'username' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    username = session['username']
    user_file = user_files_collection.find_one({"username": username})
    
    if not user_file:
        create_user_file(username)
        user_file = user_files_collection.find_one({"username": username})
    
    return jsonify({
        "success": True,
        "file": {
            "content": user_file.get('content'),
            "updated_at": user_file.get('updated_at')
        }
    }), 200

@app.route('/api/user/file', methods=['POST'])
def update_user_file():
    if 'username' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    data = request.json
    content = data.get('content')
    username = session['username']
    
    user_files_collection.update_one(
        {"username": username},
        {
            "$set": {
                "content": content,
                "updated_at": pymongo.datetime.datetime.now()
            }
        },
        upsert=True
    )
    
    return jsonify({"success": True, "message": "File updated successfully"}), 200

# Gemini AI Integration
@app.route('/api/ask', methods=['POST'])
def ask_question():
    try:
        if 'username' not in session:
            return jsonify({"success": False, "message": "Not logged in"}), 401
        
        data = request.json
        question = data.get('question')
        
        if not question:
            return jsonify({"success": False, "message": "No question provided"}), 400
        
        # Get response from Gemini
        response = model.generate_content(question)
        
        return jsonify({
            "success": True,
            "answer": response.text
        }), 200
    
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# User progress and data
@app.route('/api/user/progress', methods=['GET'])
def get_user_progress():
    if 'username' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    username = session['username']
    user = users_collection.find_one({"username": username})
    
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404
    
    progress = user.get('progress', {})
    
    return jsonify({
        "success": True,
        "progress": progress
    }), 200

@app.route('/api/user/progress', methods=['POST'])
def update_user_progress():
    if 'username' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    data = request.json
    progress = data.get('progress')
    username = session['username']
    
    users_collection.update_one(
        {"username": username},
        {"$set": {"progress": progress}}
    )
    
    return jsonify({"success": True, "message": "Progress updated successfully"}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
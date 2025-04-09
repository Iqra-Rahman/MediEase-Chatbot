import uuid
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import fitz
import pickle
import traceback
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from langchain_community.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_community.tools.tavily_search import TavilySearchResults
from typing import Annotated, Dict, List
from typing_extensions import TypedDict
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import tools_condition, ToolNode
import json
import pytz
import sqlite3
from flask import Flask, jsonify, request, send_from_directory, render_template
from langchain_core.runnables import RunnableConfig

load_dotenv()

# Load PDF's data
def load_pdf_data(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join([page.get_text("text") for page in doc])
        doc.close()
        return text if text.strip() else "No relevant data found."
    except Exception as e:
        return f"Error loading PDF: {e}"

# Check if PDF files exist and load data
pdf_path = "Sunrise Medical Center - AI-Powered Chatbot & Hospital Information.pdf"
if os.path.exists(pdf_path):
    medical_data = load_pdf_data(pdf_path)
    hospital_data = load_pdf_data(pdf_path)
    print(f"Medical data loaded: {medical_data[:100]}...")
    print(f"Hospital data loaded: {hospital_data[:100]}...")
else:
    medical_data = "Medical center data not available. Please upload the PDF file."
    hospital_data = "Hospital data not available. Please upload the PDF file."
    print("PDF not found. Using fallback data.")

# Google Calendar API setup
CLIENT_CONFIG = {
    "installed": {
        "client_id": os.getenv("CLIENT_ID"),
        "project_id": os.getenv("PROJECT_ID"),
        "auth_uri": os.getenv("AUTH_URI"),
        "token_uri": os.getenv("TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("CERT_URL"),
        "client_secret": os.getenv("CLIENT_SECRET"),
        "redirect_uris": [os.getenv("REDIRECT_URIS")]
    }
}
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
creds = None

def ensure_credentials():
    global creds
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
        if not creds.valid and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                print(f"Error refreshing credentials: {str(e)}")
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
        creds = flow.run_local_server(port=8080)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

# Initialize database schema
def initialize_database():
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_date TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        phone_number TEXT,
        email TEXT,
        city TEXT,
        message TEXT,
        event_id TEXT,
        thread_id TEXT,
        department TEXT,
        doctor TEXT
    )''')
    # Add columns if they don't exist (for backward compatibility)
    cursor.execute("PRAGMA table_info(appointments)")
    columns = [row[1] for row in cursor.fetchall()]
    if "department" not in columns:
        cursor.execute("ALTER TABLE appointments ADD COLUMN department TEXT")
    if "doctor" not in columns:
        cursor.execute("ALTER TABLE appointments ADD COLUMN doctor TEXT")
    conn.commit()
    conn.close()

# Initialize LLM
llm = ChatGroq(
    model="qwen-qwq-32b",
    api_key=os.getenv("GROQ_API_KEY")
)

# Tools

## Tool 1: Book an Appointment
@tool
def book_appointment_with_user_details(date: str, time: str, name: str, phone: str, email: str, city: str, user_message: str, department: str, doctor: str, config: RunnableConfig) -> str:
    """Books an appointment on Google Calendar and stores user details, department, and doctor in the database."""
    ensure_credentials()
    if not creds or not creds.valid:
        return "Authentication failed. Please re-authenticate."
    configuration = config.get("configurable", {})
    thread_id = configuration.get("thread_id", None)
    if not thread_id:
        return "Error: No thread ID found in configuration."

    try:
        start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_time = start_time + timedelta(hours=1)
        event = {
            "summary": "Medical Appointment",
            "location": "Sunrise Medical Center",
            "description": f"Patient: {name}\nPhone: {phone}\nEmail: {email}\nCity: {city}\nMessage: {user_message}\nDepartment: {department}\nDoctor: {doctor}",
            "start": {"dateTime": start_time.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "Asia/Kolkata"},
            "reminders": {"useDefault": False, "overrides": [{"method": "email", "minutes": 30}, {"method": "popup", "minutes": 10}]},
        }
        service = build('calendar', 'v3', credentials=creds)
        event_result = service.events().insert(calendarId='primary', body=event).execute()
        event_id = event_result.get('id')

        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO appointments 
            (appointment_date, appointment_time, patient_name, phone_number, email, city, message, event_id, thread_id, department, doctor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
            (date, time, name, phone, email, city, user_message, event_id, thread_id, department, doctor))
        conn.commit()
        conn.close()

        return f"Appointment successfully booked. Event ID: {event_id}. Assigned to {department} with {doctor}."
    except ValueError as e:
        return f"Failed to book appointment due to invalid date or time format: {str(e)}. Please use YYYY-MM-DD for date and HH:MM for time."
    except sqlite3.Error as e:
        return f"Database error: {str(e)}"
    except Exception as e:
        return f"Failed to book appointment: {str(e)}"

## Tool 2: Update an Appointment
@tool
def update_google_calendar_appointment(event_id: str, new_date: str, new_time: str, config: RunnableConfig) -> str:
    """Updates an appointment on Google Calendar and in the database."""
    ensure_credentials()
    if not creds or not creds.valid:
        return "Authentication failed. Please re-authenticate."
    configuration = config.get("configurable", {})
    current_thread_id = configuration.get("thread_id", None)
    if not current_thread_id:
        return "Error: No thread ID found in configuration."
    
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute('SELECT thread_id FROM appointments WHERE event_id = ?', (event_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return f"No appointment found with event ID {event_id}."
    
    # Authorization check removed for update to allow any thread to update appointments
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        original_start = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
        original_end = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
        duration = original_end - original_start
        new_start_time = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        new_end_time = new_start_time + duration
        event['start'] = {'dateTime': new_start_time.isoformat(), 'timeZone': 'Asia/Kolkata'}
        event['end'] = {'dateTime': new_end_time.isoformat(), 'timeZone': 'Asia/Kolkata'}
        service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        
        cursor.execute('''
            UPDATE appointments
            SET appointment_date = ?, appointment_time = ?
            WHERE event_id = ?
        ''', (new_date, new_time, event_id))
        conn.commit()
        conn.close()
        
        return f"Appointment with event ID {event_id} successfully updated to {new_date} at {new_time}."
    except ValueError as e:
        return f"Failed to update appointment due to invalid date or time format: {str(e)}. Please use YYYY-MM-DD for date and HH:MM for time."
    except Exception as e:
        return f"Failed to update appointment: {str(e)}"

## Tool 3: Cancel an Appointment
@tool
def cancel_google_calendar_appointment(event_id: str, config: RunnableConfig) -> str:
    """Cancels an appointment on Google Calendar and removes it from the database."""
    ensure_credentials()
    if not creds or not creds.valid:
        return "Authentication failed. Please re-authenticate."
    configuration = config.get("configurable", {})
    current_thread_id = configuration.get("thread_id", None)
    if not current_thread_id:
        return "Error: No thread ID found in configuration."
    
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute('SELECT thread_id FROM appointments WHERE event_id = ?', (event_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return f"No appointment found with event ID {event_id}."
    
    
    
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        
        cursor.execute('''
            DELETE FROM appointments
            WHERE event_id = ?
        ''', (event_id,))
        conn.commit()
        conn.close()
        
        return f"Appointment with event ID {event_id} successfully cancelled."
    except Exception as e:
        return f"Failed to cancel appointment: {str(e)}"

## Tool 4: Symptom Analysis
@tool
def symptom_analysis_tool(symptoms: str) -> str:
    """Analyzes user symptoms and provides possible medical conditions and relevant departments."""
    if not symptoms or not isinstance(symptoms, str):
        return "Please provide valid symptoms (e.g., 'fever, cough')."
    try:
        response = llm.invoke([
            SystemMessage(content="""You are a compassionate AI health assistant. 
            Provide friendly, concise, and informative responses based on the medical data provided.
            If the user's symptoms match an entry in the medical data, list the possible conditions and the relevant department.
            If there's no exact match, try to identify the closest related symptom(s) and provide relevant information, 
            or suggest consulting a general practitioner if no reasonable match is found.
            Do not suggest booking links, phone numbers, or specific treatments."""),
            HumanMessage(content=f"""A user is experiencing: {symptoms}.
            Based on the medical data below, provide the possible conditions and the relevant medical department.
            Medical Data:\n{medical_data}""")
        ])
        return response.content
    except Exception as e:
        return f"Error in symptom analysis: {str(e)}. Please try again or consult a healthcare provider."

## Tool 5: Hospital Info
@tool
def hospital_info_tool(query: str) -> str:
    """Provides information about hospitals, doctors, or departments based on user query."""
    if not query or not isinstance(query, str):
        return "Please provide a valid query (e.g., 'doctors in cardiology')."
    try:
        response = llm.invoke([
            SystemMessage(content="""You are a concise hospital information assistant.
            Based on the user's query and the hospital data provided, provide only the requested information.
            Supported query types:
            - Specific hospital info (e.g., 'Tell me about Hospital A'): List available departments.
            - Doctors in a department (e.g., 'doctors in cardiology'): List only doctor names, specialties, and years of experience.
            - Specific doctor info (e.g., 'Who is Dr. Smith'): Provide the doctor's specialty and experience.
            Keep responses brief and relevant. If the query doesn't match the data, say so and suggest rephrasing.
            Do not include hospital addresses, contact details, hours, fees, or links unless explicitly asked."""),
            HumanMessage(content=f"""User query: {query}.
            Based on the hospital data below, provide the specific information requested.
            Hospital Data:\n{hospital_data}""")
        ])
        return response.content
    except Exception as e:
        return f"Error retrieving hospital info: {str(e)}. Please try again."

# State Definition
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

# Assistant Class
class Assistant:
    def __init__(self, runnable):
        self.runnable = runnable

    def __call__(self, state: State, config):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            configuration = config.get("configurable", {})
            passenger_id = configuration.get("user_id", None)
            state = {**state, "user_info": passenger_id}
            
            try:
                result = self.runnable.invoke(state)
                if not result.tool_calls and (
                    not result.content or 
                    (isinstance(result.content, list) and not result.content[0].get("text"))
                ):
                    messages = state["messages"] + [HumanMessage(content="Please provide a complete response.")]
                    state = {**state, "messages": messages}
                    retry_count += 1
                else:
                    break
            except Exception as e:
                print(f"Error in Assistant: {str(e)}")
                messages = state["messages"] + [AIMessage(content="I encountered a technical issue. Please try again later.")]
                return {"messages": messages}
        
        if retry_count >= max_retries:
            messages = state["messages"] + [AIMessage(content="I'm having trouble generating a response. Please try again later.")]
            return {"messages": messages}
        
        return {"messages": state["messages"] + [result]}

# Prompt Setup
primary_assistant_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a friendly and helpful customer support assistant for Sunrise Medical Center. Your goal is to assist users in booking appointments in a conversational, step-by-step manner. The required information is: appointment date (YYYY-MM-DD format, e.g., 2025-12-25), appointment time (24-hour HH:MM format, e.g., 14:30), full name, phone number, email address, city, and reason for the appointment.\n\n"
            "When a user wants to book an appointment:\n"
            "- Start by asking only for their preferred date in YYYY-MM-DD format.\n"
            "- Once they provide the date, acknowledge it and ask for the preferred time in HH:MM format.\n"
            "- Continue this pattern, asking for one piece of information at a time: full name, phone number, email address, city, and reason for the appointment.\n"
            "- If the user provides any details in their initial message or during the conversation, acknowledge what they've given and ask for the next missing piece.\n"
            "- If a detail is in the wrong format (e.g., '25/12/2025' instead of '2025-12-25'), politely ask them to provide it in the correct format.\n"
            "- If the user has previously received a recommendation for a department and doctor based on their symptoms, use that department and doctor when booking the appointment.\n"
            "- Once all information is collected, summarize the details (including department and doctor if provided) and ask the user to confirm before booking.\n"
            "- After confirmation, call the `book_appointment_with_user_details` tool with the parameters: date, time, name, phone, email, city, user_message, department, and doctor.\n"
            "- When calling the `book_appointment_with_user_details` tool, include the `department` and `doctor` parameters if they have been recommended. If not available, ask the user for their preferred department or doctor.\n\n"
            "For updates or cancellations, ask for the event ID and guide the user step-by-step as needed, using the `update_google_calendar_appointment` or `cancel_google_calendar_appointment` tools.\n\n"
            "Always be friendly, concise, and clear in your responses, guiding the user one step at a time. Avoid using emojis and excessive formatting like asterisks.\n"
            "Current time (IST): {time}.",
        ),
        ("placeholder", "{messages}"),
    ]
).partial(time=lambda: datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"))

# Tool Setup
os.environ["TAVILY_API_KEY"] = os.getenv("TAVILY_API_KEY")
part_1_tools = [
    TavilySearchResults(max_results=1),
    book_appointment_with_user_details,
    update_google_calendar_appointment,
    cancel_google_calendar_appointment,
    symptom_analysis_tool,
    hospital_info_tool
]

# Bind Tools to LLM
part_1_assistant_runnable = primary_assistant_prompt | llm.bind_tools(part_1_tools)

# Graph Setup
builder = StateGraph(State)
builder.add_node("assistant", Assistant(part_1_assistant_runnable))
builder.add_node("tools", ToolNode(part_1_tools))
builder.add_edge(START, "assistant")
builder.add_conditional_edges("assistant", tools_condition)
builder.add_edge("tools", "assistant")
memory = MemorySaver()
part_1_graph = builder.compile(checkpointer=memory)

# Database setup
def initialize_database():
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_date TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        phone_number TEXT,
        email TEXT,
        city TEXT,
        message TEXT,
        event_id TEXT,
        thread_id TEXT,
        department TEXT,
        doctor TEXT
    )
    ''')
    # Add columns if they don't exist (for backward compatibility)
    cursor.execute("PRAGMA table_info(appointments)")
    columns = [row[1] for row in cursor.fetchall()]
    if "department" not in columns:
        cursor.execute("ALTER TABLE appointments ADD COLUMN department TEXT")
    if "doctor" not in columns:
        cursor.execute("ALTER TABLE appointments ADD COLUMN doctor TEXT")
    conn.commit()
    conn.close()

# Initialize database
initialize_database()

# Flask App Setup
app = Flask(__name__, static_folder='static')
threads = {}

@app.route('/')
def index():
    return render_template('chat copy.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"error": "Invalid request: 'message' is required"}), 400
        
        message = data['message']
        if not isinstance(message, str):
            return jsonify({"error": "Message must be a string"}), 400
        
        thread_id = data.get('thread_id')
        if not thread_id or thread_id not in threads:
            thread_id = str(uuid.uuid4())
            threads[thread_id] = part_1_graph
        
        new_message = HumanMessage(content=message)
        result = threads[thread_id].invoke(
            {"messages": [new_message]},
            config={"configurable": {"passenger_id": "User", "thread_id": thread_id}}
        )
        
        assistant_messages = [msg for msg in result["messages"] if isinstance(msg, AIMessage)]
        if not assistant_messages:
            return jsonify({"error": "No response generated"}), 500
        
        last_message = assistant_messages[-1]
        response_content = last_message.content
        
        return jsonify({
            "thread_id": thread_id,
            "response": response_content
        })
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": "Sorry, there was an error processing your request. Please try again."}), 500

@app.route('/reset', methods=['POST'])
def reset_conversation():
    try:
        data = request.get_json()
        thread_id = data.get('thread_id')
        
        if thread_id and thread_id in threads:
            threads[thread_id] = part_1_graph
            return jsonify({"status": "success", "message": "Conversation reset successfully"})
        else:
            return jsonify({"error": "Invalid thread_id"}), 400
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/appointments', methods=['GET'])
def get_appointments():
    try:
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM appointments ORDER BY appointment_date, appointment_time')
        appointments = cursor.fetchall()
        conn.close()

        appointment_list = [
            {
                "id": app[0],
                "date": app[1],
                "time": app[2],
                "name": app[3],
                "phone": app[4],
                "email": app[5],
                "city": app[6],
                "message": app[7],
                "event_id": app[8],
                "thread_id": app[9],
                "department": app[10] if len(app) > 10 else None,
                "doctor": app[11] if len(app) > 11 else None
            } for app in appointments
        ]

        return jsonify({"appointments": appointment_list})
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/clear_appointments', methods=['POST'])
def clear_appointments():
    try:
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM appointments')
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "All appointments cleared"})
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
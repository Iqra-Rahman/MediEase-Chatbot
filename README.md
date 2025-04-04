# Medical Center Chatbot

This project is an AI-powered chatbot designed for Medical Purpose. It assists users in booking, updating, and canceling medical appointments, as well as providing symptom analysis and hospital information. Built with natural language processing (NLP), the chatbot offers a conversational interface to streamline interactions with the medical center.


![1743662587657](image/README/1743662587657.png "ChatBot UI")

## Features

* **Appointment Booking** : Book appointments by providing details step-by-step, including date, time, name, phone number, email, city, and reason.
* **Appointment Management** : Update or cancel existing appointments using the event ID.
* **Symptom Analysis** : Analyze user-provided symptoms and suggest possible conditions and relevant departments.
* **Hospital Information** : Query details about hospitals, doctors, and departments.
* **Google Calendar Integration** : Manage appointments directly on Google Calendar.
* **Database Storage** : Store appointment details in an SQLite database.


## Technologies Used

* **Python** : Core programming language (version 3.8+ recommended).
* **Flask** : Web framework for the chatbot backend.
* **LangChain** : Framework for conversational AI, including LangGraph for managing conversation flow.
* **Groq** : Language model provider for natural language understanding.
* **Google Calendar API** : Handles appointment scheduling and management.
* **SQLite** : Lightweight database for storing appointment data.
* **Fitz (PyMuPDF)** : Extracts text from PDF files for medical and hospital data.


## Setup Instructions

Follow these steps to set up the project locally:

1. **Clone the Repository** :
   `git clone https://github.com/your-repo/medical-chatbot.git`
   `cd medical-chatbot`
2. **Install Dependencies** : Ensure Python 3.8+ is installed, then run
   `pip install -r requirements.txt`
3. **Set Environment Variables** :
   Create a **.env** file in the root directory and add:

   `GROQ_API_KEY=your_groq_api_key CLIENT_ID=your_google_client_id PROJECT_ID=your_google_project_id AUTH_URI=https://accounts.google.com/o/oauth2/auth TOKEN_URI=https://oauth2.googleapis.com/token CERT_URL=https://www.googleapis.com/oauth2/v1/certs CLIENT_SECRET=your_google_client_secret REDIRECT_URIS=http://localhost:8080`

   Replace placeholders with your credentials from Groq and Google Cloud.
4. **Configure Google Calendar API** :

   * Create a Google Cloud project and enable the Calendar API.
   * Generate OAuth 2.0 credentials and download the JSON file.
   * Extract values for **CLIENT_ID**, **CLIENT_SECRET**, etc., and update the **.env** file.
   * Run the script once to authenticate and generate **token.pickle**.
5. **Initialize the Database** :
   The script automatically creates an SQLite database (**appointments.db**) on first run.


## Usage

1. **Run the Flask App** :

   `python app.py`

   The application will start at **http://0.0.0.0:5000**.
2. **Interact with the Chatbot** :

* Visit **http://localhost:5000/** to access the chat interface.
* Use natural language to book appointments, manage them, or query information.

3. **API Endpoints** :

* **/chat (POST)** : Send a message to the chatbot.
* Request: **{"message": "your message", "thread_id": "optional_thread_id"}**
* Response: **{"thread_id": "thread_id", "response": "chatbot_response"}**
* **/reset (POST)** : Reset the conversation for a given thread.
* Request: **{"thread_id": "thread_id"}**
* **/appointments (GET)** : Retrieve all stored appointments.
* **/clear_appointments (POST)** : Clear all appointments from the database.


## Example Interaction

Here’s how you might book an appointment:

* **User** : I want to book an appointment.
* **Chatbot** : Sure! Let’s start with the date. Please provide your preferred appointment date in YYYY-MM-DD format (e.g., 2025-12-25).
* **User** : 2025-12-25
* **Chatbot** : Great, I’ve noted the date as 2025-12-25. Now, what time would you prefer for the appointment? Please use the 24-hour HH:MM format (e.g., 14:30).
* **User** : 14:30
* **Chatbot** : Perfect, 14:30 it is. Next, may I have your full name?
* **User** : John Doe
* **Chatbot** : Thank you, John Doe. Now, could you provide your phone number?
* **User** : 123-456-7890
* **Chatbot** : Got it. And your email address?
* **User** : [john.doe@example.com](mailto:john.doe@example.com)
* **Chatbot** : Alright. Which city are you from?
* **User** : New York
* **Chatbot** : Noted. Finally, what’s the reason for your appointment?
* **User** : Routine checkup
* **Chatbot** : Thank you. Let me summarize: You want to book an appointment on 2025-12-25 at 14:30 for a routine checkup. Your contact details are John Doe, 123-456-7890, [john.doe@example.com](mailto:john.doe@example.com), from New York. Is this correct?
* **User** : Yes
* **Chatbot** : Appointment booked successfully! Your event ID is abc123.


## Troubleshooting

* **Authentication Errors** : Delete **token.pickle** and re-authenticate if Google Calendar access fails.
* **PDF Missing** : Without the PDF, the chatbot uses fallback data, limiting symptom and hospital info.
* **Database Issues** : Ensure **appointments.db** is writable; delete and restart if corrupted.

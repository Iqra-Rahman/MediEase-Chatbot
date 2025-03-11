import fitz
from langchain.chat_models import AzureChatOpenAI
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType
from langchain.schema import SystemMessage, HumanMessage
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Azure Chat Model
llm = AzureChatOpenAI(
    deployment_name=os.getenv("DEPLOYMENT_NAME"),
    openai_api_base=os.getenv("OPENAI_API_BASE"),
    openai_api_version=os.getenv("OPENAI_API_VERSION"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

# Load PDF data
def load_pdf_data(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join([page.get_text("text") for page in doc])
        doc.close()
        return text if text.strip() else "No relevant data found."
    except Exception as e:
        return f"Error loading PDF: {e}"

medical_data = load_pdf_data(os.getenv("PDF_PATH"))
hospital_data = load_pdf_data(os.getenv("PDF_PATH"))

# Define tools
def respond_to_symptoms(user_input: str) -> str:
    """Generates a medical response based on symptoms."""
    response = llm.invoke([
        SystemMessage(content="""You are a compassionate AI health assistant. 
        Provide friendly and informative responses based on medical data. 
        Do not suggest booking links or phone numbers."""),
        HumanMessage(content=f"""A user is experiencing: {user_input}.
        Based on the medical data below, mention the possible condition and the relevant medical department.
        Medical Data:\n{medical_data}"""),
    ])
    return response.content

def get_hospital_info(query: str) -> str:
    """Fetches hospital-related information."""
    response = llm.invoke([
        SystemMessage(content="""You are a concise hospital information assistant.
        When users ask about doctors in specific departments, provide ONLY information about the doctors.
        Include ONLY their name, specialty, and years of experience.
        DO NOT include hospital address, contact details, hours, appointment information, fees, or links.
        Your response should be brief and directly answer only what was asked."""),
        HumanMessage(content=f"""User query: {query}.
        Based on the hospital data below, provide ONLY the specific information requested about doctors or departments.
        If they ask about doctors in a department, list only the doctors in that department.
        Hospital Data:\n{hospital_data}"""),
    ])
    return response.content

# Create tools
symptom_tool = Tool(
    name="Symptom Analysis Tool",
    func=respond_to_symptoms,
    description="Use this tool when a user describes medical symptoms."
)

hospital_tool = Tool(
    name="Hospital Info Tool",
    func=get_hospital_info,
    description="Use this tool when a user asks about hospitals, doctors, or departments."
)

# Initialize AI Agent
agent = initialize_agent(
    tools=[symptom_tool, hospital_tool],
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
)

# This class acts as an interface for the Flask app
class ChatAgent:
    def __init__(self, agent):
        self.agent = agent
        
    def invoke(self, user_message):
        try:
            response = self.agent.run(user_message)
            return response
        except Exception as e:
            return f"Error processing request: {e}"

# Create an instance of the ChatAgent
chat_agent = ChatAgent(agent)

if __name__ == "__main__":
    print("👋 Hi! I'm your AI health assistant. Ask about symptoms or hospital info.")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Chatbot: Take care! See you next time! 💙")
            break
        response = agent.run(user_input)
        print(f"Chatbot: {response}")
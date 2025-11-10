# Danske Bank – Intelligent Onboarding & Verification System
Cloud + Bedrock Integration (AWS Demonstration Project)

Author: Juan Pablo Rafael Zúñiga Hidalgo
📧 juanpablo.zunigah@gmail.com

📞 +46 729 971 641

1. Project Overview

This project demonstrates an end-to-end AI-assisted banking onboarding flow running fully on AWS Cloud.
The application uses React + TypeScript on the frontend and AWS Lambda, Amazon Bedrock, S3, and DynamoDB on the backend.

Users can:

Chat with an AI onboarding assistant (Bedrock Agent) to ask credit-related questions and start the registration process.

Upload their ID card, which is securely stored in S3.

Have their data automatically extracted and verified by a series of Lambda functions.

Be registered in DynamoDB if their identity is verified and not already in the system.

View all registered customers or manually check identity verification through dedicated pages.

2. Application Structure
🖥️ Frontend (React + TypeScript)

The React application provides three main pages:

Page	Path	Purpose
Home	/	Main chat interface with the Bedrock AI Agent for onboarding and credit questions.
Clients	/clients	Displays all registered customers retrieved from DynamoDB.
Verify	/verify	Allows manual identity verification using CPR/National IDs from Nordic countries.
3. Cloud Workflow and Architecture
🧩 General Logic Flow
User → Frontend (React) → Bedrock Agent → Onboarding Orchestrator (Lambda)
   ├── extract_id_from_s3 → Reads ID image from S3 and extracts data
   ├── verify_identity → Confirms ID exists in national registry
   └── create_customer → Registers verified user in DynamoDB


Each step is stateless, serverless, and isolated through specific IAM policies.

4. AWS Backend Components
🧠 Bedrock Agent

Acts as the conversational interface.

Uses deterministic instructions to manage dialogue flow.

Handles steps like consent, upload request, and validation.

Invokes the onboarding_orchestrator Lambda with session context.

Replies in professional, natural English (non-creative, rule-based).

⚙️ Lambda Functions
Lambda	Description	Key Operations
extract_id_from_s3.py	Reads an uploaded ID from S3 and extracts fields (National ID, name, DOB, country).	Uses OpenAI-powered text extraction simulation.
verify_identity.py	Simulates verification of the national ID against Swedish, Norwegian, Danish, or Finnish CPR registries.	Returns "VERIFIED", "MISMATCH", or "NOT_FOUND".
create_customer.py	Registers a verified customer in DynamoDB with idempotent writes.	Skips registration if the user already exists.
onboarding_orchestrator.py	Central router Lambda called by the Bedrock Agent.	Chains the three Lambdas above and returns combined structured JSON.
🪣 S3

Stores user-uploaded ID card images in a structured path:

db-onboard-uploads/onboard/<country>/<date>/<sessionId>/id_front.jpg

🗃️ DynamoDB

Table: DanskeBankCustomers

PK = <country>#<nationalId>

SK = PROFILE

Stores first name, last name, date of birth, email, and registration metadata.

Provides idempotent PutItem writes to avoid duplicates.

Example item:

{
  "PK": "SE#860714-1556",
  "SK": "PROFILE",
  "firstName": "Juan Pablo Rafael",
  "lastName": "Zúñiga Hidalgo",
  "email": "juanpablo.zunigahidalgo@danskebank.com",
  "status": "REGISTERED",
  "createdAt": "2025-11-10T14:05:00Z"
}

5. Frontend Logic Overview
💬 Home Page

Displays a clean hero interface with a chat launcher.

Clicking the launcher opens AgentChatWidget, which interacts with the Bedrock Agent API via agent.tsx.

Users can converse naturally and initiate the onboarding process.

🧾 Clients Page

Fetches and displays all registered customers from the DynamoDB table.

Serves as an internal view for Danske Bank personnel.

✅ Verify Page

Allows direct checking of any CPR or National ID via the verify_identity Lambda API.

Provides instant confirmation if a user is found in the simulated national registry.

6. Security and IAM Overview

Each Lambda runs under a least-privilege IAM role:

Function	Permissions
extract_id_from_s3	s3:GetObject for the upload bucket.
verify_identity	No external permissions (pure logic).
create_customer	dynamodb:PutItem, dynamodb:GetItem.
onboarding_orchestrator	lambda:InvokeFunction for the three downstream Lambdas.

No credentials are hardcoded. All secrets and ARNs are provided as Lambda environment variables.

The .env file in the frontend contains:

REACT_APP_AGENT_API=https://<lambda-url>.on.aws/
REACT_APP_API_BASE=https://<api-gateway-endpoint>


and is excluded from GitHub via .gitignore.

7. Data Privacy and Compliance

No personal data leaves the AWS environment.

All ID uploads and registry checks are simulated using mock datasets.

The system follows GDPR-style consent collection through explicit “YES” responses before ID processing.

8. Deployment Summary

Frontend (React App) → Deployed via:

npm run build
aws s3 sync build/ s3://your-frontend-bucket --delete


Lambda Functions → Deployed individually or via SAM/CDK.

DynamoDB Table → Created manually or through CloudFormation.

Bedrock Agent → Configured to call the orchestrator Lambda by ARN.

9. High-Level Architecture Diagram
flowchart TD
A[User] --> B[React Frontend]
B -->|Chat Message| C[Amazon Bedrock Agent]
C -->|Invoke| D[Onboarding Orchestrator (Lambda)]
D --> E[Extract ID from S3]
E --> F[Verify Identity]
F --> G[Create Customer in DynamoDB]
E -->|Images| H[S3 Bucket]
G --> I[DynamoDB Table]
C -->|Response| B

10. Contact

Author: Juan Pablo Rafael Zúñiga Hidalgo
📧 juanpablo.zunigah@gmail.com

📞 +46 729 971 641
🌐 LinkedIn Profile
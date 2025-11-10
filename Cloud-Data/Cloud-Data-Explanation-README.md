☁️ AWS Cloud Backend — Danske Bank Onboarding System
Overview

This folder contains the AWS Cloud backend logic for the Danske Bank Intelligent Onboarding System.
It defines the Lambda functions, data flow, and agent orchestration that operate behind the frontend user interface.

All components are designed for secure, modular integration within AWS and are orchestrated by an Amazon Bedrock Agent that manages the entire conversation flow with the user.

🧩 Components and Flow
1. onboarding_orchestrator.py

The central Lambda function that coordinates the onboarding process.
It acts as a router that connects the Bedrock Agent with specific backend tasks.

When invoked, it:

Receives structured input from the Bedrock Agent.

Determines the current onboarding step.

Sequentially triggers the other Lambdas:

extract_id_from_s3

verify_identity

create_customer

Returns a structured response back to Bedrock for conversational output.

This orchestration ensures that all backend operations follow a deterministic, traceable pipeline within AWS.

2. extract_id_from_s3.py

This Lambda reads the uploaded ID image from a specified S3 bucket.

Input: { "bucket": "<name>", "sessionId": "<uuid>", "country": "<DK/SE/NO/FI>" }

Process:

Loads the file from S3.

Simulates OCR extraction to identify fields like:

First Name

Last Name

Date of Birth

National ID (CPR)

Returns extracted data with a confidence score.

Output: JSON with extracted fields.

If confidence < 0.9, the orchestrator asks the user to re-upload the ID.

3. verify_identity.py

This Lambda simulates an identity check against mock national registries (Sweden, Denmark, Norway, Finland).

Input: Extracted ID data.

Process:

Validates that all required fields are present.

Checks the national ID pattern and country consistency.

Returns "status": "VERIFIED" if data is valid, otherwise "status": "UNVERIFIED".

Output: A standardized verification object used by downstream functions.

This module is fully stateless and contains no external dependencies.

4. create_customer.py

Handles customer registration in Amazon DynamoDB.

Input: Verified identity data.

Process:

Constructs a unique partition key: PK = <country>#<nationalId>.

Uses an idempotent write (ConditionExpression="attribute_not_exists(PK)") to avoid duplicates.

If the record exists, it returns "User already registered".

Otherwise, it stores a new entry with metadata:

customerId (UUID)

email (auto-generated)

createdAt timestamp.

Output: Registration confirmation message.

DynamoDB table:
DanskeBankCustomers
Primary key: PK
Sort key: "PROFILE"

🧠 Bedrock Agent Integration

The Bedrock Agent acts as the conversation brain.
It doesn’t store data — it routes intents to AWS Lambda functions via the onboarding_orchestrator.

Workflow Summary:
User → Frontend → Bedrock Agent → onboarding_orchestrator →
  ├── extract_id_from_s3
  ├── verify_identity
  └── create_customer → DynamoDB


Each Lambda returns structured JSON, allowing Bedrock to produce deterministic, human-like responses such as:

Thank you. You are now registered.
Email: firstname.lastname@danskebank.com
ID: --1556

🔐 AWS IAM and Security Policies

Each Lambda function operates under a least-privilege IAM role:

Lambda	Permissions
extract_id_from_s3	s3:GetObject for the ID bucket.
verify_identity	No external permissions (pure logic).
create_customer	dynamodb:PutItem, dynamodb:GetItem on DanskeBankCustomers.
onboarding_orchestrator	lambda:InvokeFunction for all other Lambdas.

All credentials, ARNs, and environment variables are configured in the Lambda console (not in code).

🗃️ Environment Variables (Example)
Key	Description
FN_EXTRACT_ID	ARN of the extract_id_from_s3 Lambda
FN_VERIFY_ID	ARN of the verify_identity Lambda
FN_CREATE_CUSTOMER	ARN of the create_customer Lambda
UPLOAD_BUCKET	S3 bucket for uploaded IDs
TABLE_NAME	DynamoDB customer table
🧾 Notes

All modules are stateless and serverless, scaling automatically on AWS Lambda.

The design ensures data isolation per session using UUID-based session IDs.

ChatGPT was used during prototyping for logic refinement, but no personal data leaves AWS during operation.

This backend can be easily extended with Amazon Rekognition or Textract for real OCR and KYC compliance.
# Deploy Doctor Support on AWS (EC2 + Bedrock)

This guide is for a new user to:
- create an EC2 instance
- deploy this Doctor Support app
- use AWS Bedrock for the LLM (instead of OpenAI/Ollama)

## 0) Prereqs (local machine)

- AWS account + billing enabled
- AWS CLI installed (`aws --version`)
- `ssh` installed

### Choose a region

Pick a Bedrock-supported region you plan to deploy into (example: `ap-south-1`).

Set it once in your shell:
```bash
export AWS_REGION="ap-south-1"
export AWS_DEFAULT_REGION="$AWS_REGION"
```

## 1) Create AWS credentials (new user)

Recommended: use an **IAM role on EC2** (no long-lived keys on the server).

You still need local credentials to create EC2 resources. You can do this with:
- AWS SSO (recommended), or
- an IAM user access key (works, but not ideal)

### Option A: Use AWS SSO (recommended)

1. Configure SSO:
```bash
aws configure sso
```
2. Login:
```bash
aws sso login
```

### Option B: Create an IAM user via AWS CLI (basic)

Create user:
```bash
aws iam create-user --user-name doctor-support-admin
```

Attach minimal policies (for demo; tighten later):
```bash
aws iam attach-user-policy --user-name doctor-support-admin --policy-arn arn:aws:iam::aws:policy/AmazonEC2FullAccess
aws iam attach-user-policy --user-name doctor-support-admin --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-user-policy --user-name doctor-support-admin --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
```

Create access key:
```bash
aws iam create-access-key --user-name doctor-support-admin
```

Configure locally:
```bash
aws configure
```

## 2) Enable Bedrock model access (one-time)

This step is usually done in the AWS Console:
- Bedrock → Model access → Request access for the model you want (example: Claude / Llama / Titan).

Without model access, Bedrock calls will fail even if IAM permissions are correct.

## 3) Create an EC2 instance (Ubuntu)

### 3.1 Create a key pair (for SSH)

```bash
aws ec2 create-key-pair \
  --key-name doctor-support-key \
  --query 'KeyMaterial' \
  --output text > doctor-support-key.pem

chmod 400 doctor-support-key.pem
```

### 3.2 Create a Security Group (allow SSH + app ports)

```bash
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
SG_ID="$(aws ec2 create-security-group \
  --group-name doctor-support-sg \
  --description "Doctor Support SG" \
  --vpc-id "$VPC_ID" \
  --query 'GroupId' --output text)"

aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 8501 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 8000 --cidr 0.0.0.0/0
```

Tip: lock SSH to your IP instead of `0.0.0.0/0`.

### 3.3 Launch the instance

Use a recent Ubuntu AMI. AMI IDs vary by region; fetch it dynamically:
```bash
UBUNTU_AMI_ID="$(aws ssm get-parameters \
  --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query 'Parameters[0].Value' --output text)"

INSTANCE_ID="$(aws ec2 run-instances \
  --image-id "$UBUNTU_AMI_ID" \
  --instance-type t3.medium \
  --key-name doctor-support-key \
  --security-group-ids "$SG_ID" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=doctor-support}]' \
  --query 'Instances[0].InstanceId' --output text)"

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
PUBLIC_IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
echo "EC2 Public IP: $PUBLIC_IP"
```

## 4) SSH into EC2 and install dependencies

```bash
ssh -i doctor-support-key.pem ubuntu@"$PUBLIC_IP"
```

On EC2:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git ffmpeg
```

## 5) Deploy the app code

On EC2 (pick a folder):
```bash
mkdir -p ~/apps
cd ~/apps
git clone https://gitlab.com/digital-coworker-group/healthcare.git
cd healthcare
```

Create venv and install:
```bash
python3 -m venv doctor-venv
source doctor-venv/bin/activate
pip install -r requirements.txt
```

## 6) Configure environment variables on EC2

### 6.1 Brevo email (required for sending mail)

```bash
export BREVO_API_KEY="..."
export BREVO_SENDER_EMAIL="..."
export BREVO_SENDER_NAME="Doctor Support"
export BREVO_DEFAULT_TO_EMAIL="..."
```

### 6.2 Bedrock (LLM)

This repo supports Bedrock via env:
- `LLM_PROVIDER=bedrock`
- `BEDROCK_REGION` and `BEDROCK_MODEL_ID`

Operational prerequisites:
- EC2 instance role/user must have permissions for `bedrock:InvokeModel` (and optionally `bedrock:InvokeModelWithResponseStream`)
- model access must be enabled in Bedrock console

Example (Claude Haiku 4.5):
```bash
export LLM_PROVIDER="bedrock"
export BEDROCK_REGION="us-east-1"   # must match where you enabled Bedrock model access
export BEDROCK_MODEL_ID="anthropic.claude-haiku-4-5-20251001-v1:0"
```

If you want to use Ollama instead:
```bash
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="ollama"
export OPENAI_MODEL="llama3.2:3b"
export API_BASE_URL="http://localhost:11434/v1"
```

## Local Postgres (optional)

Run Postgres locally with Docker:
```bash
docker run --name doctor-support-postgres \\
  -e POSTGRES_PASSWORD=postgres \\
  -e POSTGRES_DB=doctor_support \\
  -p 5432:5432 \\
  -d postgres:16
```

Set `DATABASE_URL`:
```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/doctor_support"
```

## 7) Run the services

### Backend (FastAPI)

```bash
source doctor-venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend (Streamlit)

In a second SSH session:
```bash
cd ~/apps/healthcare
source doctor-venv/bin/activate
python -m streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

Open in browser:
- Streamlit: `http://<PUBLIC_IP>:8501`
- Backend docs: `http://<PUBLIC_IP>:8000/docs`

## 8) Production notes (recommended)

- Put Streamlit + API behind Nginx on port 80/443.
- Use `systemd` to run both services on boot.
- Don’t keep secrets in shell history; store them in AWS SSM Parameter Store or Secrets Manager.
- Restrict Security Group ingress (don’t expose 8000/8501 publicly in production).

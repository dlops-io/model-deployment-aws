#!/bin/bash

# This script helps you set up AWS credentials securely
# DO NOT commit this file to git if you add your actual credentials!

echo "Setting up AWS credentials for model deployment..."
echo "Choose an option:"
echo "1. Use existing AWS CLI configuration (~/.aws/credentials)"
echo "2. Set environment variables temporarily"
echo "3. Create a secrets file"

read -p "Enter your choice (1-3): " choice

case $choice in
    1)
        echo "Using existing AWS CLI configuration..."
        echo "Make sure you have run 'aws configure' before."
        ;;
    2)
        echo "Enter your AWS credentials (they will be set as environment variables for this session only):"
        read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID
        read -sp "AWS Secret Access Key (hidden): " AWS_SECRET_ACCESS_KEY
        echo
        read -p "AWS Region (default: us-east-1): " AWS_REGION
        AWS_REGION=${AWS_REGION:-us-east-1}
        read -p "SageMaker Execution Role ARN: " SAGEMAKER_ROLE
        
        export AWS_ACCESS_KEY_ID
        export AWS_SECRET_ACCESS_KEY
        export AWS_REGION
        export SAGEMAKER_ROLE
        
        echo "Credentials set for this session."
        echo "Now run: sh docker-shell.sh"
        ;;
    3)
        echo "Creating secrets file..."
        SECRETS_DIR="../secrets"
        mkdir -p $SECRETS_DIR
        
        read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID
        read -sp "AWS Secret Access Key (hidden): " AWS_SECRET_ACCESS_KEY
        echo
        read -p "AWS Region (default: us-east-1): " AWS_REGION
        AWS_REGION=${AWS_REGION:-us-east-1}
        read -p "SageMaker Execution Role ARN: " SAGEMAKER_ROLE
        
        cat > $SECRETS_DIR/aws-credentials.sh << EOF
#!/bin/bash
# AWS Credentials - DO NOT COMMIT THIS FILE TO GIT!
export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
export AWS_REGION="$AWS_REGION"
export SAGEMAKER_ROLE="$SAGEMAKER_ROLE"
export S3_MODELS_BUCKET_NAME="cheese-app-models-demo"
EOF
        
        chmod 600 $SECRETS_DIR/aws-credentials.sh
        echo "Secrets file created at $SECRETS_DIR/aws-credentials.sh"
        echo "This file has been protected with restrictive permissions (600)"
        echo ""
        echo "To use it, run:"
        echo "  source $SECRETS_DIR/aws-credentials.sh"
        echo "  sh docker-shell.sh"
        ;;
    *)
        echo "Invalid choice. Please run the script again."
        exit 1
        ;;
esac

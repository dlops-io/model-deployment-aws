#!/bin/bash

echo "Container is running!!!"

# Configure AWS CLI if credentials are provided
if [ ! -z "$AWS_ACCESS_KEY_ID" ] && [ ! -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Configuring AWS credentials..."
    aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
    aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
    [ ! -z "$AWS_SESSION_TOKEN" ] && aws configure set aws_session_token $AWS_SESSION_TOKEN
    aws configure set region $AWS_REGION
fi

# Test AWS connectivity
echo "Testing AWS connectivity..."
aws sts get-caller-identity

#/bin/bash
pipenv shell

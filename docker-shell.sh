#!/bin/bash

set -e

export IMAGE_NAME=model-deployment-cli-aws
export BASE_DIR=$(pwd)
export SECRETS_DIR=$(pwd)/../secrets/
export AWS_REGION="us-east-1"
export S3_MODELS_BUCKET_NAME="cheese-app-models-demo"

# Load AWS credentials from secrets file if it exists
if [ -f "$SECRETS_DIR/aws-credentials.sh" ]; then
    echo "Loading AWS credentials from secrets file..."
    source "$SECRETS_DIR/aws-credentials.sh"
else
    echo "Warning: No secrets file found at $SECRETS_DIR/aws-credentials.sh"
    echo "Using AWS credentials from environment or ~/.aws/credentials"
fi

# Ensure we have the necessary environment variables
if [ -z "$SAGEMAKER_ROLE" ]; then
    echo "Warning: SAGEMAKER_ROLE not set. You'll need to provide it when deploying."
fi

# Build the image based on the Dockerfile
#docker build -t $IMAGE_NAME -f Dockerfile .
# M1/2 chip macs use this line
docker build -t $IMAGE_NAME --platform=linux/arm64/v8 -f Dockerfile .

# Run Container
docker run --rm --name $IMAGE_NAME -ti \
-v "$BASE_DIR":/app \
-v "$SECRETS_DIR":/secrets \
-v ~/.aws:/home/app/.aws \
-e AWS_REGION=$AWS_REGION \
-e S3_MODELS_BUCKET_NAME=$S3_MODELS_BUCKET_NAME \
-e SAGEMAKER_ROLE=$SAGEMAKER_ROLE \
-e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
-e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
-e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
$IMAGE_NAME
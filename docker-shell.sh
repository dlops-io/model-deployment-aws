#!/bin/bash

set -e

export IMAGE_NAME=model-deployment-cli-aws
export BASE_DIR=$(pwd)
export S3_MODELS_BUCKET_NAME="cheese-app-models-demo"
export SAGEMAKER_ROLE="arn:aws:iam::931210546037:role/model-deployment-sagemaker"
export AWS_REGION="us-east-1"

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
-v ~/.aws:/home/app/.aws \
-e AWS_REGION=$AWS_REGION \
-e S3_MODELS_BUCKET_NAME=$S3_MODELS_BUCKET_NAME \
-e SAGEMAKER_ROLE=$SAGEMAKER_ROLE \
$IMAGE_NAME
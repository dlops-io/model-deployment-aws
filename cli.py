"""
Module that contains the command line app.

Typical usage example from command line:
        python cli.py --upload
        python cli.py --deploy
        python cli.py --predict
        python cli.py --delete
"""

import os
import requests
import zipfile
import tarfile
import argparse
from glob import glob
import numpy as np
import json
import boto3
import sagemaker
from sagemaker.tensorflow import TensorFlowModel
from sagemaker import get_execution_role
from sagemaker.serializers import JSONSerializer
from sagemaker.deserializers import JSONDeserializer
import tensorflow as tf
from datetime import datetime
from PIL import Image
from botocore.exceptions import ClientError

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_MODELS_BUCKET_NAME = os.environ["S3_MODELS_BUCKET_NAME"]
BEST_MODEL = "model-mobilenetv2_train_base_True.v1"
ARTIFACT_URI = f"s3://{S3_MODELS_BUCKET_NAME}/{BEST_MODEL}"
SAGEMAKER_ROLE = os.environ.get("SAGEMAKER_ROLE", "")

data_details = {
    "image_width": 224,
    "image_height": 224,
    "num_channels": 3,
    "num_classes": 4,
    "label2index": {"parmigiano": 0, "gruyere": 1, "brie": 2, "gouda": 3},
    "index2label": {"0": "parmigiano", "1": "gruyere", "2": "brie", "3": "gouda"},
}


def download_file(packet_url, base_path="", extract=False, headers=None):
    if base_path != "":
        if not os.path.exists(base_path):
            os.mkdir(base_path)
    packet_file = os.path.basename(packet_url)
    with requests.get(packet_url, stream=True, headers=headers) as r:
        r.raise_for_status()
        with open(os.path.join(base_path, packet_file), "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    if extract:
        if packet_file.endswith(".zip"):
            with zipfile.ZipFile(os.path.join(base_path, packet_file)) as zfile:
                zfile.extractall(base_path)
        else:
            with tarfile.open(os.path.join(base_path, packet_file)) as tfile:
                tfile.extractall(base_path)


def prepare():
    # Initialize S3 client
    s3_client = boto3.client("s3", region_name=AWS_REGION)

    # Create bucket if it doesn't exist
    try:
        if AWS_REGION == "us-east-1":
            s3_client.create_bucket(Bucket=S3_MODELS_BUCKET_NAME)
        else:
            s3_client.create_bucket(
                Bucket=S3_MODELS_BUCKET_NAME,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
            )
    except s3_client.exceptions.BucketAlreadyExists:
        print(f"Bucket {S3_MODELS_BUCKET_NAME} already exists")
    except s3_client.exceptions.BucketAlreadyOwnedByYou:
        print(f"Bucket {S3_MODELS_BUCKET_NAME} already owned by you")

    download_file(
        "https://github.com/dlops-io/model-deployment-aws/releases/download/v1.0/mobilenetv2_train_base_True.zip",
        base_path="artifacts",
        extract=True,
    )

    prediction_model_path = (
        "./artifacts/mobilenetv2_train_base_True.keras"
    )

    # Load model
    prediction_model = tf.keras.models.load_model(prediction_model_path)

    # Save model locally first
    local_model_dir = f"./artifacts/{BEST_MODEL}"
    os.makedirs(local_model_dir, exist_ok=True)

    # Save model in TensorFlow SavedModel format
    model_export_path = os.path.join(
        local_model_dir, "1"
    )  # SageMaker expects version number

    # Export using Keras 3 export() if available, otherwise fall back to tf.saved_model.save
    if hasattr(prediction_model, "export"):
        print("Using Keras 3 export()")
        prediction_model.export(model_export_path)
    else:
        print("Using tf.saved_model.save()")
        tf.saved_model.save(prediction_model, model_export_path)

    # Create tar.gz archive for SageMaker
    model_tar_path = f"{local_model_dir}/model.tar.gz"
    with tarfile.open(model_tar_path, "w:gz") as tar:
        tar.add(model_export_path, arcname="1")

    # Upload to S3
    s3_key = f"{BEST_MODEL}/model.tar.gz"
    print(f"Uploading model to s3://{S3_MODELS_BUCKET_NAME}/{s3_key}")
    s3_client.upload_file(model_tar_path, S3_MODELS_BUCKET_NAME, s3_key)
    print("Model uploaded successfully to S3")


def deploy():
    # Initialize SageMaker session
    sagemaker_session = sagemaker.Session()

    # Get execution role - you need to set this in environment or use IAM role
    if SAGEMAKER_ROLE:
        role = SAGEMAKER_ROLE
    else:
        # This works if running on SageMaker notebook instance or with proper IAM setup
        try:
            role = get_execution_role()
        except Exception as e:
            print(f"Error getting execution role: {e}")
            print(
                "Please set SAGEMAKER_ROLE environment variable with your SageMaker execution role ARN"
            )
            print(
                "Example: arn:aws:iam::123456789012:role/service-role/AmazonSageMaker-ExecutionRole"
            )
            return

    # Model artifact location in S3
    model_data = f"s3://{S3_MODELS_BUCKET_NAME}/{BEST_MODEL}/model.tar.gz"

    # Create SageMaker model
    tensorflow_model = TensorFlowModel(
        model_data=model_data,
        role=role,
        framework_version="2.13",
        sagemaker_session=sagemaker_session,
        name=BEST_MODEL.replace(".", "-").replace(
            "_", "-"
        ),  # SageMaker naming requirements
    )

    # Deploy model to endpoint
    print("Deploying model to SageMaker endpoint...")
    # Create a timestamped endpoint name to avoid collisions
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    endpoint_name = (
        BEST_MODEL.replace(".", "-").replace("_", "-") + f"-endpoint-{ts}"
    )
    predictor = tensorflow_model.deploy(
        initial_instance_count=1,
        instance_type="ml.m5.xlarge",
        endpoint_name=endpoint_name,
        serializer=JSONSerializer(),
        deserializer=JSONDeserializer(),
    )

    print("Model deployed successfully!")
    print(f"Endpoint name: {predictor.endpoint_name}")
    print(f"To invoke the endpoint, use endpoint name: {predictor.endpoint_name}")

    # Save endpoint configuration for later use
    endpoint_config = {"endpoint_name": predictor.endpoint_name, "region": AWS_REGION}

    with open("endpoint_config.json", "w") as f:
        json.dump(endpoint_config, f, indent=2)
    print("Endpoint configuration saved to endpoint_config.json")


def predict():
    # Load endpoint configuration
    try:
        with open("endpoint_config.json", "r") as f:
            endpoint_config = json.load(f)
        endpoint_name = endpoint_config["endpoint_name"]
    except FileNotFoundError:
        print("Error: endpoint_config.json not found. Please deploy the model first.")
        print("You can also manually set the endpoint name in the code.")
        endpoint_name = BEST_MODEL.replace(".", "-").replace("_", "-") + "-endpoint"

    # Build a SageMaker Predictor that speaks JSON
    predictor = sagemaker.Predictor(
        endpoint_name=endpoint_name,
        sagemaker_session=sagemaker.Session(),
        serializer=JSONSerializer(),
        deserializer=JSONDeserializer(),
    )

    # Get a sample image to predict
    image_files = glob(os.path.join("data", "*.jpg"))
    image_files.extend(glob(os.path.join("data", "*.jpeg")))
    print("image_files:", image_files[:5])

    if not image_files:
        print("No image files found in data directory")
        return

    image_samples = np.random.randint(0, high=len(image_files), size=min(5, len(image_files)))
    for img_idx in image_samples:
        img_path = image_files[img_idx]
        print("Image:", img_path)

        with Image.open(img_path) as img:
            img = img.convert("RGB").resize((224, 224))
            arr = np.asarray(img, dtype=np.float32) / 255.0

        payload = {"instances": [arr.tolist()]}

        try:
            result = predictor.predict(payload)
            print("Result:", result)
            if "predictions" in result:
                prediction = result["predictions"][0]
                prediction_index = int(np.argmax(prediction))
                print(prediction, prediction_index)
                print("Label:   ", data_details["index2label"][str(prediction_index)], "\n")
            else:
                print("Unexpected response format:", result)
        except Exception as e:
            print(f"Error invoking endpoint: {e}")
            print(f"Make sure the endpoint '{endpoint_name}' exists and is in service")


def delete():
    # Load endpoint configuration if present
    endpoint_name = None
    try:
        with open("endpoint_config.json", "r") as f:
            endpoint_config = json.load(f)
            endpoint_name = endpoint_config.get("endpoint_name")
    except FileNotFoundError:
        pass

    sm_client = boto3.client("sagemaker", region_name=AWS_REGION)
    s3_client = boto3.client("s3", region_name=AWS_REGION)

    # Delete endpoint
    if endpoint_name:
        try:
            print(f"Deleting endpoint: {endpoint_name}")
            sm_client.delete_endpoint(EndpointName=endpoint_name)
        except ClientError as e:
            print(f"Warning: could not delete endpoint {endpoint_name}: {e}")

    # Try to derive endpoint-config and model names from our naming scheme
    model_name = BEST_MODEL.replace(".", "-").replace("_", "-")
    endpoint_config_name = None

    # Best-effort: list endpoint configs and delete ones referencing our model
    try:
        paginator = sm_client.get_paginator("list_endpoint_configs")
        for page in paginator.paginate():
            for ec in page.get("EndpointConfigs", []):
                name = ec.get("EndpointConfigName", "")
                if model_name in name:
                    endpoint_config_name = name
                    print(f"Deleting endpoint config: {endpoint_config_name}")
                    try:
                        sm_client.delete_endpoint_config(EndpointConfigName=endpoint_config_name)
                    except ClientError as e:
                        print(f"Warning: could not delete endpoint config {endpoint_config_name}: {e}")
    except ClientError as e:
        print(f"Warning: list_endpoint_configs failed: {e}")

    # Delete model
    try:
        print(f"Deleting model: {model_name}")
        sm_client.delete_model(ModelName=model_name)
    except ClientError as e:
        print(f"Warning: could not delete model {model_name}: {e}")

    # Delete S3 artifacts under BEST_MODEL/
    prefix = f"{BEST_MODEL}/"
    try:
        print(f"Deleting S3 artifacts s3://{S3_MODELS_BUCKET_NAME}/{prefix}")
        paginator = s3_client.get_paginator("list_objects_v2")
        to_delete = []
        for page in paginator.paginate(Bucket=S3_MODELS_BUCKET_NAME, Prefix=prefix):
            for obj in page.get("Contents", []):
                to_delete.append({"Key": obj["Key"]})
                if len(to_delete) == 1000:
                    s3_client.delete_objects(Bucket=S3_MODELS_BUCKET_NAME, Delete={"Objects": to_delete})
                    to_delete = []
        if to_delete:
            s3_client.delete_objects(Bucket=S3_MODELS_BUCKET_NAME, Delete={"Objects": to_delete})
    except ClientError as e:
        print(f"Warning: could not delete S3 artifacts: {e}")
    
    # Remove local endpoint_config.json
    try:
        os.remove("endpoint_config.json")
        print("Removed endpoint_config.json")
    except FileNotFoundError:
        pass


def main(args=None):

    if args.prepare:
        print("Prepare model and save model to GCS Bucket")
        prepare()

    elif args.deploy:
        print("Deploy model")
        deploy()

    elif args.predict:
        print("Predict using endpoint")
        predict()

    elif args.delete:
        print("Delete endpoint, model, and S3 artifacts")
        delete()


if __name__ == "__main__":
    # Generate the inputs arguments parser
    # if you type into the terminal 'python cli.py --help', it will provide the description
    parser = argparse.ArgumentParser(description="Data Collector CLI")

    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Prepare model and save model to GCS Bucket",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Deploy saved model to Vertex AI",
    )
    parser.add_argument(
        "--predict",
        action="store_true",
        help="Make prediction using the endpoint from Vertex AI",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test deployment to Vertex AI",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete endpoint, endpoint config, model, and S3 artifacts",
    )

    args = parser.parse_args()

    main(args)

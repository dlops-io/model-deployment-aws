"""
Module that contains the command line app.

Typical usage example from command line:
        python cli.py --upload
        python cli.py --deploy
        python cli.py --predict
"""

import os
import requests
import zipfile
import tarfile
import argparse
from glob import glob
import numpy as np
import base64
import json
import boto3
import sagemaker
from sagemaker.tensorflow import TensorFlowModel
from sagemaker import get_execution_role
import tensorflow as tf

# # W&B
# import wandb

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

    # Use this code if you want to pull your model directly from WandB
    # WANDB_KEY = os.environ["WANDB_KEY"]
    # # Login into wandb
    # wandb.login(key=WANDB_KEY)

    # # Download model artifact from wandb
    # run = wandb.init()
    # artifact = run.use_artifact(
    #     "ac215-harvard/cheese-app-demo/model-mobilenetv2_train_base_True",
    #     type="model",
    # )
    # artifact_dir = artifact.download()
    # print("artifact_dir", artifact_dir)

    # Download model
    download_file(
        "https://github.com/dlops-io/models/releases/download/v3.0/mobilenetv2_train_base_True.zip",
        base_path="artifacts",
        extract=True,
    )
    prediction_model_path = (
        "./artifacts/mobilenetv2_train_base_True/mobilenetv2_train_base_True.keras"
    )

    # Load model
    prediction_model = tf.keras.models.load_model(prediction_model_path)
    # print(prediction_model.summary())

    # Preprocess Image
    def preprocess_image(bytes_input):
        decoded = tf.io.decode_jpeg(bytes_input, channels=3)
        decoded = tf.image.convert_image_dtype(decoded, tf.float32)
        resized = tf.image.resize(decoded, size=(224, 224))
        return resized

    @tf.function(input_signature=[tf.TensorSpec([None], tf.string)])
    def preprocess_function(bytes_inputs):
        decoded_images = tf.map_fn(
            preprocess_image, bytes_inputs, dtype=tf.float32, back_prop=False
        )
        return {"model_input": decoded_images}

    @tf.function(input_signature=[tf.TensorSpec([None], tf.string)])
    def serving_function(bytes_inputs):
        images = preprocess_function(bytes_inputs)
        results = model_call(**images)
        return results

    model_call = tf.function(prediction_model.call).get_concrete_function(
        [tf.TensorSpec(shape=[None, 224, 224, 3], dtype=tf.float32, name="model_input")]
    )

    # Save model locally first
    local_model_dir = f"./artifacts/{BEST_MODEL}"
    os.makedirs(local_model_dir, exist_ok=True)

    # Save model in TensorFlow SavedModel format
    model_export_path = os.path.join(
        local_model_dir, "1"
    )  # SageMaker expects version number
    tf.saved_model.save(
        prediction_model,
        model_export_path,
        signatures={"serving_default": serving_function},
    )

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

    # Note: TensorFlowModel will automatically use the appropriate container image
    # based on the framework_version parameter

    # Create SageMaker model
    tensorflow_model = TensorFlowModel(
        model_data=model_data,
        role=role,
        framework_version="2.12",
        sagemaker_session=sagemaker_session,
        name=BEST_MODEL.replace(".", "-").replace(
            "_", "-"
        ),  # SageMaker naming requirements
    )

    # Deploy model to endpoint
    print("Deploying model to SageMaker endpoint...")
    predictor = tensorflow_model.deploy(
        initial_instance_count=1,
        instance_type="ml.m5.xlarge",
        endpoint_name=BEST_MODEL.replace(".", "-").replace("_", "-") + "-endpoint",
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
        # Fallback to a default endpoint name or prompt user to deploy first
        endpoint_name = BEST_MODEL.replace(".", "-").replace("_", "-") + "-endpoint"

    # Initialize SageMaker runtime client
    runtime_client = boto3.client("sagemaker-runtime", region_name=AWS_REGION)

    # Get a sample image to predict
    image_files = glob(os.path.join("data", "*.jpg"))
    image_files.extend(glob(os.path.join("data", "*.jpeg")))
    print("image_files:", image_files[:5])

    if not image_files:
        print("No image files found in data directory")
        return

    image_samples = np.random.randint(
        0, high=len(image_files), size=min(5, len(image_files))
    )
    for img_idx in image_samples:
        print("Image:", image_files[img_idx])

        with open(image_files[img_idx], "rb") as f:
            image_data = f.read()

        # Convert image to base64
        b64str = base64.b64encode(image_data).decode("utf-8")

        # Format the request for TensorFlow Serving
        # The serving_default signature expects bytes_inputs
        payload = {"instances": [b64str]}  # Send base64 encoded string directly

        try:
            # Invoke endpoint
            response = runtime_client.invoke_endpoint(
                EndpointName=endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload),
            )

            # Parse response
            result = json.loads(response["Body"].read().decode())

            print("Result:", result)

            # Extract predictions
            if "predictions" in result:
                prediction = result["predictions"][0]
                prediction_index = prediction.index(max(prediction))
                print(prediction, prediction_index)
                print(
                    "Label:   ",
                    data_details["index2label"][str(prediction_index)],
                    "\n",
                )
            else:
                print("Unexpected response format:", result)

        except Exception as e:
            print(f"Error invoking endpoint: {e}")
            print(f"Make sure the endpoint '{endpoint_name}' exists and is in service")


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

    args = parser.parse_args()

    main(args)

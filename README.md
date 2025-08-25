# Cheese App: Model Deployment Demo - AWS Version

In this tutorial we will deploy a model to AWS SageMaker:
<img src="images/serverless-model-deployment.png"  width="800">

## Setup Environments
In this tutorial we will setup a container to manage building and deploying models to AWS SageMaker Model Registry and Endpoints.

### Clone the github repository
- Clone or download from [here](https://github.com/dlops-io/model-deployment-aws)

### AWS Services to Enable
Make sure you have access to the following AWS services:
* Amazon S3
* Amazon SageMaker
* AWS IAM

### AWS Credentials
Next step is to enable our container to have access to S3 buckets & SageMaker in AWS.

#### Create AWS IAM User
1. Go to the [AWS Console](https://console.aws.amazon.com/)
2. Navigate to IAM (Identity and Access Management)
3. Create a new IAM user called "model-deployment"
4. Attach the following policies:
   - `AmazonS3FullAccess`
   - `AmazonSageMakerFullAccess`
   - `IAMFullAccess` (needed for SageMaker to create execution roles)
5. Create access keys for this user
6. Save the Access Key ID and Secret Access Key

#### Create SageMaker Execution Role

SageMaker needs an execution role to access AWS resources on your behalf:

1. Go to the AWS Console > IAM > Roles
2. Click "Create role"
3. Choose "SageMaker" as the trusted entity
4. Attach the following policies:
   - `AmazonSageMakerFullAccess`
   - `AmazonS3FullAccess`
5. Name the role "SageMakerExecutionRole"
6. Copy the Role ARN (it will look like: `arn:aws:iam::123456789012:role/SageMakerExecutionRole`)
7. Save this ARN - you'll need it for the SAGEMAKER_ROLE environment variable

### Create S3 Bucket

We need a bucket to store the saved model files that will be used by SageMaker to deploy models.

- Go to `https://console.aws.amazon.com/s3/`
- Create a bucket `cheese-app-models-demo` [REPLACE WITH YOUR UNIQUE BUCKET NAME]
  - Note: S3 bucket names must be globally unique across all AWS accounts

## Run Container

### ⚠️ SECURITY WARNING
**NEVER hardcode AWS credentials directly in scripts or commit them to Git!**
If you see credentials in any script files, remove them immediately.

### Configure AWS Credentials

You can provide credentials/config via either the AWS CLI config or direct env vars.

#### Option 1: AWS CLI Configuration (Recommended)
Run the following command on your local machine:
```bash
aws configure
```
Enter your:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., us-east-1)
- Default output format (json)

This will create `~/.aws/credentials` and `~/.aws/config` files that will be mounted into the container.

#### Option 2: Environment Variables
Export the following environment variables before running the container:
```bash
export AWS_ACCESS_KEY_ID=your_access_key_id
export AWS_SECRET_ACCESS_KEY=your_secret_access_key
export AWS_REGION=us-east-1
```

### Update Configuration

Edit `docker-shell.sh` to update:
- `S3_MODELS_BUCKET_NAME`: Your S3 bucket name
- `SAGEMAKER_ROLE`: The arn for the role you previously created
- `AWS_REGION`

### Quick Start Commands

Once you've set up your credentials, here's the typical workflow:

```bash
# 1. Build and run the container
chmod +x docker-shell.sh
sh docker-shell.sh

# 2. Inside the container, prepare and deploy your model
python cli.py --prepare
python cli.py --deploy
python cli.py --predict

# 3. When done, delete resources to avoid charges
python cli.py --delete
```

### Prepare Model for Deployment
Our model weights are stored following the serverless training we did in the previous tutorials. In this step, we'll download the model and then upload it to an S3 bucket, enabling SageMaker to access it for deployment to an endpoint.

* Run `python cli.py --prepare`, this will:
  1. Download the model from GitHub
  2. Prepare the model in TensorFlow SavedModel format
  3. Package it as model.tar.gz (required by SageMaker)
  4. Upload to the specified S3 bucket

### Upload & Deploy Model to SageMaker
In this step we create a SageMaker model and deploy it as an endpoint.

* Run `python cli.py --deploy`, this will:
  1. Create a SageMaker model from the S3 artifacts
  2. Deploy the model to a SageMaker endpoint
  3. Save the endpoint configuration to `endpoint_config.json`

* This will take several minutes to complete (typically 5-10 minutes)
* Once the model has been deployed, the endpoint name will be displayed
* The endpoint configuration will be saved to `endpoint_config.json` for future use

### Test Predictions

* Run `python cli.py --predict`
* The script will automatically load the endpoint configuration from `endpoint_config.json`
* You should see results similar to this:
```
Predict using endpoint
image_files: ['data/brie-1.jpg', 'data/brie-2.jpg', 'data/gouda-1.jpg', 'data/gouda-2.jpeg', 'data/gruyere-1.jpg']
Image: data/brie-2.jpg
Result: {'predictions': [[0.0887121782, 0.0439011417, 0.867386699]]}
[0.0887121782, 0.0439011417, 0.867386699] 2
Label:    brie 

Image: data/gouda-1.jpg
Result: {'predictions': [[0.986440122, 0.00689249625, 0.0066674049]]}
[0.986440122, 0.00689249625, 0.0066674049] 0
Label:    gouda 
```

## Clean Up Resources

To avoid ongoing charges, make sure to delete the SageMaker endpoint when you're done:

### Using AWS Console:
1. Go to SageMaker > Endpoints
2. Select your endpoint
3. Click "Delete"

### Using AWS CLI:
```bash
aws sagemaker delete-endpoint --endpoint-name <your-endpoint-name>
aws sagemaker delete-endpoint-config --endpoint-config-name <your-endpoint-config-name>
aws sagemaker delete-model --model-name <your-model-name>
```

### Using the CLI Script
You can now run the built-in delete command to remove the deployed resources and uploaded artifacts:
```bash
python cli.py --delete
```
It will attempt to delete:
- The SageMaker endpoint from `endpoint_config.json` (if present)
- The corresponding endpoint configuration and model (best-effort by name convention)
- The S3 artifacts under `s3://$S3_MODELS_BUCKET_NAME/$BEST_MODEL/`

Make sure to confirm in your AWS console to avoid charges.

## Troubleshooting

### Common Issues:

1. **Permission Denied Errors**:
   - Ensure your IAM user/role has the necessary permissions
   - Check that the SageMaker execution role has access to S3

2. **Endpoint Creation Fails**:
   - Verify the model.tar.gz was uploaded correctly to S3
   - Check CloudWatch logs for detailed error messages in your endpoint

3. **Predictions Fail**:
   - Ensure the endpoint is in "InService" status
   - Verify the input format matches what the model expects
   - Check that image files exist in the data directory

4. **S3 Bucket Already Exists**:
   - S3 bucket names must be globally unique
   - Choose a different bucket name with your unique identifier

## Additional Resources

- [AWS SageMaker Documentation](https://docs.aws.amazon.com/sagemaker/)
- [SageMaker TensorFlow Serving](https://sagemaker.readthedocs.io/en/stable/frameworks/tensorflow/deploying_tensorflow_serving.html)
- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
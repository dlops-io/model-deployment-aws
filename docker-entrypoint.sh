#!/bin/bash

echo "Container is running!!!"

# Test AWS connectivity
echo "Testing AWS connectivity..."
aws sts get-caller-identity

#/bin/bash
pipenv shell

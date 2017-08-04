#!/bin/bash

# Ensure AWS environment variables are set
if [ -z ${AWS_ACCESS_KEY_ID} ]; then
    echo "You must set the environment variable 'AWS_ACCESS_KEY_ID'"
    exit 1
elif [ -z ${AWS_SECRET_ACCESS_KEY ]; then
    echo "You must set the environment variable 'AWS_SECRET_ACCESS_KEY'"
fi

# Ensure python dependencies are installed
if ! python -c "import boto" &> /dev/null; then
    echo "The python package 'boto' must be installed"
fi1

# Refresh AWS dynamic inventory
./inventory/aws/hosts/ec2.py --refresh-cache

ansible-playbook deploy-cluster.yaml --extra-vars "@vars/main.yaml"
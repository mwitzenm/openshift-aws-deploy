# OpenShift 3.5 on Amazon Web Services
This repository contains scripts for deploying an OpenShift Container Platform cluster to a single AWS AZ. It borrows heavily from the official Red Hat [OpenShift AWS Reference Architecture](https://github.com/openshift/openshift-ansible-contrib/tree/master/reference-architecture/aws-ansible).

## Overview
The Ansible playbooks here use [cloudformation modules](http://docs.ansible.com/ansible/latest/cloudformation_module.html) to spin up all of the required AWS infrastructure and then leverage the official [OpenShift playbooks](https://github.com/openshift/openshift-ansible/tree/release-1.5/playbooks/byo) provided by Red Hat to do the installation. This method will deploy 3 Masters, 3 infrastructure nodes, and 2 applcation nodes to a single AWS availability zone. You can find the cloudformation template at [playbooks/roles/create-cloudformation-stack/files](playbooks/roles/create-cloudformation-stack/files).

The biggest difference between this repository and the official reference architecture is the use of a single availability zone and no default identity provider.

## Prerequisites
A registered domain must be added to Route53 as a Hosted Zone before installation.  This registered domain can be purchased through AWS.

It is also assumed that these scripts are being run from a RHEL server.

### Required subscriptions and packages
```
$ subscription-manager repos --enable rhel-7-server-optional-rpms
$ subscription-manager repos --enable rhel-7-server-ose-3.5-rpms
$ subscription-manager repos --enable rhel-7-fast-datapath-rpms
$ yum -y install atomic-openshift-utils ansible openshift-ansible-playbooks
$ rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
$ yum -y install python2-boto \
                 pyOpenSSL \
                 git \
                 python-netaddr \
                 python-six \
                 python2-boto3 \
                 python-click \
                 python-httplib2
$ git clone https://github.com/nccurry/openshift-aws-deploy.git
```

### Modify SSH Config
Due to the installations use of a bastion server the ssh config must be modified.
You should replace ```*.domain.com``` and ```bastion.domain.com``` with your own domain name that is configured in Route 53 and point the config at the ssh key you intend to use.
```
$ vim /home/user/.ssh/config
Host *.domain.com
     ProxyCommand               ssh ec2-user@bastion -W %h:%p
     IdentityFile               /path/to/ssh/key

Host bastion
     Hostname                   bastion.domain.com
     user                       ec2-user
     StrictHostKeyChecking      no
     ProxyCommand               none
     CheckHostIP                no
     ForwardAgent               yes
     IdentityFile               /path/to/ssh/key

```
### Export the EC2 Credentials
You will need to export your EC2 credentials before attempting to use the
scripts:
```
export AWS_ACCESS_KEY_ID=foo
export AWS_SECRET_ACCESS_KEY=bar
```

### Set required parameters
You can get the list of accepted parameters by running ```$ ./deploy-cluster -h```
```shell
$ ./deploy-cluster.py -h
Usage: deploy-cluster.py [OPTIONS]

Options:
  --stack-name TEXT               Cloudformation stack name. Must be unique
                                  [default: openshift-infra]
  --console-port INTEGER RANGE    OpenShift web console port  [default: 443]
  --deployment-type [origin|openshift-enterprise]
                                  OpenShift deployment type  [default:
                                  openshift-enterprise]
  --openshift-sdn TEXT            OpenShift SDN (redhat/openshift-ovs-subnet,
                                  redhat/openshift-ovs-multitenant, or other
                                  supported SDN)  [default: redhat/openshift-
                                  ovs-subnet]
  --region TEXT                   ec2 region  [default: us-east-1]
  --availability_zone TEXT        ec2 availability zone  [default: us-east-1a]
  --ami TEXT                      ec2 ami  [default: ami-a33668b4]
  --master-instance-type TEXT     ec2 instance type  [default: m4.xlarge]
  --node-instance-type TEXT       ec2 instance type  [default: t2.large]
  --app-instance-type TEXT        ec2 instance type  [default: t2.large]
  --bastion-instance-type TEXT    ec2 instance type  [default: t2.micro]
  --keypair TEXT                  ec2 keypair name
  --create-key TEXT               Create SSH keypair  [default: no]
  --key-path TEXT                 Path to SSH public key. Default is /dev/null
                                  which will skip the step  [default:
                                  /dev/null]
  --create-vpc TEXT               Create VPC  [default: yes]
  --vpc-id TEXT                   Specify an already existing VPC
  --private-subnet-id1 TEXT       Specify a Private subnet within the existing
                                  VPC
  --public-subnet-id1 TEXT        Specify a Public subnet within the existing
                                  VPC
  --public-subnet-id2 TEXT        Specify a Public subnet within the existing
                                  VPC
  --public-subnet-id3 TEXT        Specify a Public subnet within the existing
                                  VPC
  --public-hosted-zone TEXT       hosted zone for accessing the environment
  --app-dns-prefix TEXT           application dns prefix  [default: apps]
  --rhsm-user TEXT                Red Hat Subscription Management User
  --rhsm-password TEXT            Red Hat Subscription Management Password
  --rhsm-pool TEXT                Red Hat Subscription Management Pool Name
  --byo-bastion TEXT              skip bastion install when one exists within
                                  the cloud provider  [default: no]
  --bastion-sg TEXT               Specify Bastion Security group used with
                                  byo-bastion  [default: /dev/null]
  --containerized TEXT            Containerized installation of OpenShift
                                  [default: False]
  --s3-bucket-name TEXT           Bucket name for S3 for registry
  --s3-username TEXT              S3 user for registry access
  --deploy-openshift-metrics [true|false]
                                  Deploy OpenShift Metrics
  --openshift-hosted-metrics-storage-volume-size TEXT
                                  Size of OptionShift Metrics Persistent
                                  Volume
  --no-confirm                    Skip confirmation prompt
  -h, --help                      Show this message and exit.
  -v, --verbose
```

#### Region
The default region is us-east-1 but can be changed when running the deploy-cluster.py script by specifying --region=us-west-2 for example.

#### AMI ID
The AMI ID may need to change if the AWS IAM account does not have access to the Red Hat Cloud Access gold image. You can follow steps [here](https://access.redhat.com/articles/2962171) for details on the Red Hat Cloud Access gold image.

#### Containerized Installation
Specifying the configuration trigger --containerized=true will install and run OpenShift services in containers. Both Atomic Host and RHEL can run OpenShift in containers. When using Atomic Host the version of docker must be 1.10 or greater and the configuration trigger --containerized=true must be used or OpenShift will not operate as expected.

## Deploy Cluster
```shell
$ ./deploy-cluster.py \
  --stack-name='dev' \
  --openshift-sdn='redhat/openshift-ovs-multitenant' \
  --ami='ami-9d2f098f' \
  --master-instance-type='t2.large' \
  --node-instance-type='t2.large' \
  --app-instance-type='t2.large' \
  --bastion-instance-type='t2.micro' \
  --keypair='OSE-key' \
  --create-key='yes' \
  --key-path='/home/user/.ssh/id_rsa.pub' \
  --public-hosted-zone='domain.com' \
  --rhsm-user='rh-user' \
  --rhsm-password='password' \
  --rhsm-pool='Red Hat OpenShift Container Platform, Standard, 2-Core'
```
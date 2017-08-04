# OpenShift 3.5 on Amazon Web Services
This repository contains ansible playbooks for deploying an OpenShift Container Platform cluster to a single AWS AZ. 

## Overview
The Ansible playbooks here use [cloudformation modules](http://docs.ansible.com/ansible/latest/cloudformation_module.html) to spin up all of the required AWS infrastructure and then leverage the official [OpenShift playbooks](https://github.com/openshift/openshift-ansible/tree/release-1.5/playbooks/byo) provided by Red Hat to do the installation. This method will deploy 3 Masters, 3 infrastructure nodes, and 2 applcation nodes to a single AWS availability zone. You can find the cloudformation template at [cfn-templates/](cfn-templates/).

## Prerequisites
* Appropriate Red Hat Subscriptions for OpenShift enterprise
* A target RHEL 7 ami (either [AWS provided](https://aws.amazon.com/marketplace/pp/B00KWBZVK6) or using the [cloud access gold image](https://access.redhat.com/articles/2962171))
* A registered domain must be added to Route53 as a Hosted Zone before installation.
* AWS IAM user with permissions to create (delete permissions are also helpful for testing):
    * Accounts
    * S3 Buckets
    * Roles
    * Policies
    * Route53 Entries
    * Elastic Load Balancers
    * EC2 Instances
* A RHEL 7 server with sudo permissions that playbooks will run from
* TLS certificates for OCP Master and Router if desired

### Configuring RHEL Ansible server
#### Installing required packages
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
```

#### Configure SSH for use with Bastion
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
You can find more information about using an SSH bastion [here](http://blog.scottlowe.org/2015/11/21/using-ssh-bastion-host/).

#### Export the EC2 Credentials
You will need to export your EC2 credentials before attempting to use the
scripts:
```
export AWS_ACCESS_KEY_ID=foo
export AWS_SECRET_ACCESS_KEY=bar
```

### Clone playbooks and set required parameters
To run the installation you will need to clone this repository and modify the parameters to meet your cluster requirements.
```shell
$ git clone https://github.com/nccurry/openshift-aws-deploy
$ cd openshift-aws-deploy
```
#### Deployment parameters
The file at [var/main.yaml](var/main.yaml) contains parameters required for deployment of the infstructure and is a few cases for cluster installation. 

At a minimum you will need to add values for the following:
* ami
* public_hosted_zone
* rhsm_user
* rhsm_password
* rhsm_pool

#### Cluster parameters
You may also want to modify the parameters for the OpenShift cluster installation. Typically this is done via an [ansible hosts](https://docs.openshift.com/container-platform/3.5/install_config/install/advanced_install.html) file.

However this installation method automatically moves from AWS infrastructure deployment to cluster installation. If you wish to modify cluster parameters the values are passed to the official OpenShift ansible playbook in the following file [tasks/openshift-install.yaml](tasks/openshift-install.yaml)

## Deploy Cluster
```shell
$ ansible-playbook deploy-cluster.yaml --extra-vars "@vars/main.yaml"
```
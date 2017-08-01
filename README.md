# OpenShift 3.5 on Amazon Web Services
This repository contains scripts for deploying an OpenShift Container Platform cluster to a single AWS AZ. It borrows heavily from the official [Red Hat OpenShift AWS Reference Architecture](https://github.com/openshift/openshift-ansible-contrib/tree/master/reference-architecture/aws-ansible).

## Overview
The repository contains Ansible playbooks which deploy 3 Masters, 3 infrastructure nodes, and 2 applcation nodes to a single AWS availability zone. These scripts only currently support OpenShift 3.5. The playbooks deploy a Docker registry and scale the router to the number of Infrastruture nodes.

The biggest difference between this repository and the official reference architecture is the use of a single availability zone and no default identity provider.

## Prerequisites
A registered domain must be added to Route53 as a Hosted Zone before installation.  This registered domain can be purchased through AWS.


### Deployment of OpenShift Enterprise
The code in this repository leverages the Ansible cloudformation modules to spin up all of the required AWS infrastructure. It then relies on the official OpenShift playbooks from the atomic-openshift-utils rpm provided by Red Hat. It is assumed you are running the following from a RHEL box.

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

### Before Launching the Ansible script
Due to the installations use of a bastion server the ssh config must be modified.
You should replace ```*.domain.com``` and ```bastion.domain.com``` with your own domain name that is configured in Route 53.
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

### Region
The default region is us-east-1 but can be changed when running the deploy-cluster.py script by specifying --region=us-west-2 for example.

### AMI ID
The AMI ID may need to change if the AWS IAM account does not have access to the Red Hat Cloud Access gold image. You can follow steps [here](https://access.redhat.com/articles/2962171) for details on the Red Hat Cloud Access gold image.

### Containerized Installation
Specifying the configuration trigger --containerized=true will install and run OpenShift services in containers. Both Atomic Host and RHEL can run OpenShift in containers. When using Atomic Host the version of docker must be 1.10 or greater and the configuration trigger --containerized=true must be used or OpenShift will not operate as expected.

### New AWS Environment (Greenfield)
When installing into an new AWS environment perform the following.   This will create the SSH key, bastion host, and VPC for the new environment.

**OpenShift Container Platform**
```
./ose-on-aws.py --keypair=OSE-key --create-key=yes --key-path=/path/to/ssh/key.pub --rhsm-user=rh-user --rhsm-password=password \
--public-hosted-zone=sysdeseng.com --rhsm-pool="Red Hat OpenShift Container Platform, Standard, 2-Core" \
--github-client-secret=47a0c41f0295b451834675ed78aecfb7876905f9 --github-organization=openshift \
--github-organization=RHSyseng --github-client-id=3a30415d84720ad14abc --deploy-openshift-metrics=true

```

If the SSH key that you plan on using in AWS already exists then perform the following.

**OpenShift Container Platform**
```
./ose-on-aws.py --keypair=OSE-key --rhsm-user=rh-user --rhsm-password=password --public-hosted-zone=sysdeseng.com --rhsm-pool="Red Hat OpenShift Container Platform, Standard, 2-Core"

```

### Existing AWS Environment (Brownfield)
If installing OpenShift Container Platform or OpenShift Origin into an existing AWS VPC perform the following. The script will prompt for vpc and subnet IDs.  The Brownfield deployment can also skip the creation of a Bastion server if one already exists. For mappings of security groups make sure the bastion security group is named bastion-sg.

**OpenShift Container Platform**
```
./ose-on-aws.py --create-vpc=no --byo-bastion=yes --keypair=OSE-key --rhsm-user=rh-user --rhsm-password=password \
--public-hosted-zone=sysdeseng.com --rhsm-pool="Red Hat OpenShift Container Platform, Standard, 2-Core" --bastion-sg=sg-a32fa3 \
--github-client-secret=47a0c41f0295b451834675ed78aecfb7876905f9 --github-organization=openshift \
--github-organization=RHSyseng --github-client-id=3a30415d84720ad14abc
```

## Multiple OpenShift deployments
The same greenfield and brownfield deployment steps can be used to launch another instance of the reference architecture environment. When launching a new environment ensure that the variable stack-name is changed. If the variable is not changed the currently deployed environment may be changed.

**OpenShift Container Platform**
```
./ose-on-aws.py --rhsm-user=rh-user --public-hosted-zone=rcook-aws.sysdeseng.com --keypair=OSE-key \
--rhsm-pool="Red Hat OpenShift Container Platform, Standard, 2-Core" --keypair=OSE-key --rhsm-password=password \
--stack-name=prod --github-client-secret=47a0c41f0295b451834675ed78aecfb7876905f9 --github-organization=openshift \
--github-organization=RHSyseng --github-client-id=3a30415d84720ad14abc
```

## Adding nodes 
Adding nodes can be done by performing the following. The configuration option --node-type allows for the creation of application or
infrastructure nodes. If the deployment is for an application node --infra-sg and --infra-elb-name are not required.

If `--use-cloudformation-facts` is not used the `--iam-role` or `Specify the name of the existing IAM Instance Profile:`
is available visiting the IAM Dashboard and selecting the role sub-menu. Select the
node role and record the information from the `Instance Profile ARN(s)` line. An
example Instance Profile would be `OpenShift-Infra-NodeInstanceProfile-TNAGMYGY9W8K`.

If the Reference Architecture deployment is >= 3.5

```
$ ./add-node.py --existing-stack=dev --rhsm-user=rhsm-user --rhsm-password=password
--public-hosted-zone=sysdeseng.com --keypair=OSE-key --rhsm-pool="Red Hat OpenShift Container Platform, Premium, 2-Core"
--use-cloudformation-facts --shortname=ose-infra-node04 --node-type=infra --subnet-id=subnet-0a962f4
```

## Teardown

A playbook is included to remove the s3 bucket and cloudformation. The parameter ci=true should not be used unless there is 100% certanty that all unattached EBS volumes can be removed.

```
ansible-playbook -i inventory/aws/hosts -e 'region=us-east-1 stack_name=openshift-infra ci=false' playbooks/teardown.yaml
```
If nodes were added to the environment the following can be ran. Below shows all of the possible teardown additions.
```
ansible-playbook -i inventory/aws/hosts -e 'region=us-east-1 stack_name=openshift-infra ci=true' -e 'extra_app_nodes=openshift-infra-ose-app-node03' -e 'gluster_nodes=openshift-infra-cns' -e 'extra_infra_nodes=openshift-infra-ose-infra-node04' playbooks/teardown.yaml
```

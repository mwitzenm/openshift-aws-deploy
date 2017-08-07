#!/usr/bin/env python

import click
import os
import sys
import yaml
import json
from typing import Dict, Tuple
from boto.cloudformation import CloudFormationConnection, connect_to_region

@click.command()
@click.option('--deployment_type',
              default='cluster',
              type=click.Choice(['cluster', 'infra-node', 'app-node']),
              help='Are you deploying a new cluster or adding a new node?',
              show_default=True)
@click.option('--stack_arn',
              help='If adding a new cluster node, the ARN of the existing CloudFormation stack is required.')
@click.option('--clear_known_hosts',
              is_flag=True,
              help='Adding this flag will delete the known hosts file at ~/.ssh/known_hosts')
@click.help_option('--help', '-h')
@click.option('-v', '--verbose', count=True)
def launch(deployment_type=None, stack_arn=None, clear_known_hosts=None, verbose=None):
    # Prompt for CloudFormation stack ARN if adding a node to a cluster
    if deployment_type in ['infra-node', 'app-node'] and stack_arn is None:
        stack_arn = click.prompt("Please enter the CloudFormation stack ARN of the cluster you wish to scale up.")

    # Clear known_hosts file between cluster deployments
    if clear_known_hosts is True:
        if os.path.isfile('~/.ssh/known_hosts'):
            print "Clearing known_hosts file at ~/.ssh/known_hosts"
            os.system("rm -rf ~/.ssh/known_hosts")

    # Generate new CloudFormation template if adding new node
    if deployment_type in ['infra-node', 'app-node']:
        cfn_conn = get_cfn_conn()
        curr_template = get_cfn_template(cfn_conn, stack_arn)
        next_node_name, next_ec2_name = generate_new_node_keys(deployment_type, curr_template)
        new_template = generate_new_cfn_template(next_node_name, next_ec2_name, curr_template)
        new_template_json = json.dumps(new_template)
        validate_cfn_template(cfn_conn, new_template_json)

    # Clear dynamic inventory cache
    print "Refreshing dynamic inventory cache"
    os.system('inventory/aws/hosts/ec2.py --refresh-cache > /dev/null')

    # Remove cached ansible facts
    if os.path.isdir('.ansible'):
        print "Removing cached ansible facts"
        os.system('rm -rf .ansible')

    # Run playbook
    status = os.system('ansible-playbook deploy-cluster.yaml --extra-vars "@vars/main.yaml" -e "deployment_type=%s"' % deployment_type)
    if os.WIFEXITED(status) and os.WEXITSTATUS(status) != 0:
        sys.exit(os.WEXITSTATUS(status))


def get_cfn_conn():
    # type: () -> CloudFormationConnection
    """Creates CloudFormation connection object using region data in vars/main.yaml"""

    # Open vars/main.yaml. Used to get AWS region
    with open('vars/main.yaml', mode='r') as f:
        try:
            vars = yaml.load(f)
        except yaml.YAMLError as e:
            print("There was a problem loading 'vars/main.yaml. \n%s" % e.message)
            exit(1)

    # Get CloudFormation connection
    try:
        cfn_conn = connect_to_region(region_name=vars['region'])
    except Exception as e:
        print("There was a problem connecting to AWS. \n%s" % e.message)
        exit(1)

    return cfn_conn


def get_cfn_template(cfn_conn, stack_arn):
    # type: (CloudFormationConnection, str) -> Dict
    """Get CloudFormation stack template using ARN"""

    # Get CloudFormation template
    try:
        cfn_get_template = cfn_conn.get_template(stack_name_or_id=stack_arn)
    except Exception as e:
        print("There was a problem connecting to AWS. %s" % e.message)
        exit(1)

    # The actual template body is returned as a string. Marshal to dictionary
    try:
        cfn_template = json.loads(cfn_get_template['GetTemplateResponse']['GetTemplateResult']['TemplateBody'])
    except Exception as e:
        print("There was a problem marshaling the template body. \n%s" % e.message)
        exit(1)

    return cfn_template


def generate_new_node_keys(deploy_type, curr_template):
    # type: (str, Dict) -> Tuple[str, str]
    """Generate new template values for new node from current template i.e. AppNode03/ose-app-node03"""\

    # Set node label for CloudFormation template, based on scale up type
    node_prefix = "InfraNode" if deploy_type == "infra-node" else 'AppNode'
    node_ec2_prefix = "ose-infra-node" if deploy_type == "infra-node" else "ose-app-node"

    # The CloudFormation template references nodes in the resources section by
    # 'AppNode01' or 'InfraNode03'. In order to add a new node to the template, we
    # need to determine which node is being added (i.e. If there are already 2 AppNode's
    # then we will be adding AppNode03). The following is some list comprehension black
    # magic to determine the number of the next node in the sequence based on the current
    # template.
    # This almost certainly should get replaced by something more readable.
    # Resources -> Just those starting with 'AppNode/InfraNode' -> Max of the int of the last chars as string -> Add one and leading zeroes
    try:
        next_node_no = str(max([int(k[-2:]) for k in curr_template['Resources'].iterkeys() if k.startswith(node_prefix)]) + 1).zfill(2)
    except KeyError as e:
        print("The CloudFormation JSON returned by AWS was not in the expected format. \nMissing key %s" % e.message)
    except Exception as e:
        print("There was a problem reading the CloudFormation template to discover the new node value. \n%s" % e.message)
        exit(1)

    # Create template labels. These values are used in the CloudFormation template
    next_node_name = node_prefix + next_node_no # e.g AppNode + 03 -> AppNode03
    next_ec2_name = node_ec2_prefix + next_node_no # e.g ose-infra-node + 04 -> ose-infra-node04

    return next_node_name, next_ec2_name


def generate_new_cfn_template(next_node_name, next_ec2_name, curr_template):
    # type: (str, str, Dict) -> Dict
    """Modify existing CloudFormation template to include new cluster node.

    Properly adding a new OpenShift cluster node to the CloudFormation template
    requires changes in 2/3 places depending on whether you're adding an app node
    or an infra node.
    For infra only:
        - Add the new node to the router ELB (Resources.InfraElb.Properties.Instances)
    For either:
        - Add a Route53 A record for the new node (Resources.Route53Records.Properties.RecordSets)
        - Add the EC2 instance definition (Resources)
    """
    # TODO: The guts of this function are abhorrent. Devise cleaner way

    # TODO: Figure out whether there is a better way to use a single source of truth for template objects
    # If scaling up an infra node, we need to add the new node to the router ELB
    if next_node_name[:-2] is "InfraNode":
        curr_template["Resources"]["InfraElb"]["Properties"]["Instances"].append({"Ref": next_node_name})

    # Add Route 53 Records
    new_record = {
        "Name": {"Fn::Join": [".", [next_ec2_name, {"Ref": "Route53HostedZone"}]]},
        "Type": "A",
        "TTL": "300",
        "ResourceRecords": [{"Fn::GetAtt": [next_node_name, "PrivateIp"]}]
    }
    curr_template["Resources"]["Route53Records"]["Properties"]["RecordSets"].append(new_record)

    # Add EC2 instance by copying existing template
    curr_template["Resources"][next_node_name] = curr_template["Resources"][next_node_name[:-2] + "01"]

    # Update EC2 instance values
    new_name_tag_value = {"Fn::Join": [".", [next_ec2_name,{"Ref": "PublicHostedZone"}]]}

    for i, tag in enumerate(curr_template["Resources"][next_node_name]["Properties"]["Tags"]):
        if tag["Key"] == "Name":
            curr_template["Resources"][next_node_name]["Properties"]["Tags"][i]["Value"] = new_name_tag_value

    return curr_template


def validate_cfn_template(cfn_conn, template):
    # type: (CloudFormationConnection, dict) -> None
    """Validates a CloudFormation template using the AWS API"""

    try:
        resp = cfn_conn.validate_template(template)
    except Exception as e:
        print("The CloudFormation template was invalid. \n%s" % e.message)
        exit(1)


if __name__ == '__main__':
    # Ensure AWS environment variables have been set
    if os.getenv('AWS_ACCESS_KEY_ID') is None or os.getenv('AWS_SECRET_ACCESS_KEY') is None:
        print 'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be exported as environment variables.'
        sys.exit(1)

    launch()
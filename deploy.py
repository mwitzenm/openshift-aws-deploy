#!/usr/bin/env python

import click
import os
import sys
import boto.cloudformation
import yaml
import json

@click.command()
@click.option('--deployment_type',
              default='cluster',
              type=click.Choice(['cluster', 'infra-node', 'app-node']),
              help='Are you deploying a new cluster or adding a new node?',
              show_default=True)
@click.option('--stack_arn',
              help='If adding a new cluster node, the ARN of the existing CloudFormation stack is required.')
@click.help_option('--help', '-h')
@click.option('-v', '--verbose', count=True)
def launch(deployment_type=None, stack_arn=None, verbose=None):
    # Prompt for CloudFormation stack ARN if adding a node to a cluster
    if deployment_type in ['infra-node', 'app-node'] and stack_arn is None:
        stack_arn = click.prompt("Please enter the CloudFormation stack ARN of the cluster you wish to scale up.")

    # Generate new CloudFormation template if adding new node
    if deployment_type in ['infra-node', 'app-node']:
        cfn_template = get_cfn_template(stack_arn)
        new_template = generate_new_cfn_template(deployment_type, cfn_template)

    # # Clear dynamic inventory cache
    # os.system('inventory/aws/hosts/ec2.py --refresh-cache > /dev/null')
    #
    # # Remove cached ansible facts
    # os.system('rm -rf .ansible/cached_facts')
    #
    # # Run playbook
    # status = os.system('ansible-playbook deploy-cluster.yaml --extra-vars "@vars/main.yaml deployment_type=%s"' % deployment_type)
    # if os.WIFEXITED(status) and os.WEXITSTATUS(status) != 0:
    #     sys.exit(os.WEXITSTATUS(status))


def get_cfn_template(stack_arn):
    # Load variables file in
    with open('vars/main.yaml', mode='r') as f:
        try:
            vars = yaml.load(f)
        except yaml.YAMLError as e:
            print("There was a problem loading 'vars/main.yaml. \n%s" % e.message)
            exit(1)

    # Connect to CloudFormation, pull down existing stack template
    try:
        cfn = boto.cloudformation.connect_to_region(region_name=vars['region'])
        cfn_get_template = cfn.get_template(stack_name_or_id=stack_arn)
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


# TODO: The guts of this function are abhorrent. Devise cleaner way
def generate_new_cfn_template(deployment_type, current_template):
    # Set node label for CloudFormation template, based on scale up type
    node_prefix = "InfraNode" if deployment_type == "infra-node" else 'AppNode'
    node_ec2_prefix = "ose-infra-node" if deployment_type == "infra-node" else "ose-app-node"

    # The CloudFormation template references nodes in the resources section by
    # 'AppNode01' or 'InfraNode03'. In order to add a new node to the template, we
    # need to determine which node is being added (i.e. If there are already 2 AppNode's
    # then we will be adding AppNode03). The following is some list comprehension black
    # magic to determine the number of the next node in the sequence based on the current
    # template.
    # This almost certainly should get replaced by something more readable.
    # Resources -> Just those starting with 'AppNode/InfraNode' -> Max of the int of the last chars as string -> Add one and leading zeroes
    try:
        next_node_no = str(max([int(k[-2:]) for k in current_template['Resources'].iterkeys() if k.startswith(node_prefix)]) + 1).zfill(2)
    except KeyError as e:
        print("The CloudFormation JSON returned by AWS was not in the expected format. \nMissing key %s" % e.message)
    except Exception as e:
        print("There was a problem reading the CloudFormation template to discover the new node value. \n%s" % e.message)
        exit(1)

    # Create template labels. These values are used in the CloudFormation template
    next_node_name = node_prefix + next_node_no # e.g AppNode + 03 -> AppNode03
    next_ec2_name = node_ec2_prefix + next_node_no # e.g ose-infra-node + 04 -> ose-infra-node04

    # TODO: Figure out whether there is a better way to use a single source of truth for template objects
    # If scaling up an infra node, we need to add the new node to the router ELB
    if node_prefix is "InfraNode":
        current_template["Resources"]["InfraElb"]["Properties"]["Instances"].append({"Ref": next_node_name})

    # Add Route 53 Records
    new_record = {
        "Name": {"Fn::Join": [".", [next_ec2_name, {"Ref": "Route53HostedZone"}]]},
        "Type": "A",
        "TTL": "300",
        "ResourceRecords": [{"Fn::GetAtt": [next_node_name, "PrivateIp"]}]
    }
    current_template["Resources"]["Route53Records"]["Properties"]["RecordSets"].append(new_record)

    # Add EC2 instance by copying existing template
    current_template["Resources"][next_node_name] = current_template["Resources"][next_node_name[:-2]+"01"]

    # Update EC2 instance values
    new_name_tag_value = {"Fn::Join": [".", [next_ec2_name,{"Ref": "PublicHostedZone"}]]}

    for i, tag in enumerate(current_template["Resources"][next_node_name]["Properties"]["Tags"]):
        if tag["Key"] == "Name":
            current_template["Resources"][next_node_name]["Properties"]["Tags"][i]["Value"] = new_name_tag_value

    print json.dumps(current_template)

    # TODO: Required changes for scaling up app node
    # Resources.Route53Records.Properties.RecordSets
    # Resources.AppNode##

    # TODO: Required changes for scaling up infra node
    # Resources.InfraElb.Properties.Instances
    # Resources.Route53Records.Properties.RecordSets
    # Resources.InfraNode##

if __name__ == '__main__':
    # Ensure AWS environment variables have been set
    if os.getenv('AWS_ACCESS_KEY_ID') is None or os.getenv('AWS_SECRET_ACCESS_KEY') is None:
        print 'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be exported as environment variables.'
        sys.exit(1)

    launch()
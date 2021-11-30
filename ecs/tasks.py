import datetime
import json
import pprint
import sys
import time

import boto3
from botocore.exceptions import ClientError
from invoke import run, task

from .definitions.sqs_worker import register_sqs_worker_tasks

AWS_REGION  = 'us-east-1'
SQS_WORKER_QUEUE_NAME = 'iotile-worker-prod'

SECURITY_GROUPS = ['sg-94c298ee']

ECS_CONFIG = {
    'CLUSTER_NAME': 'iotile-cloud-cluster',
    'TASK_FORMAT': 'iotile-cloud-{}-task',
    'SERVICE_FORMAT': 'iotile-cloud-{}-service',
    'WORKER_NAME': 'sqs-worker',
    'AMI': 'ami-aff65ad2',
    'INSTANCE_TYPE': 't2.small',
    'INSTANCE_MIN_COUNT': 2,
    'INSTANCE_MAX_COUNT': 2,
    'INSTANCE_ROLE': 'ecsInstanceIotileRole',
    'WORKERS_COUNT': 3
}

def wait_until_ec2_state_changes(ec2_client, ec2_instance_ids, desired_state):
    all_synced = False
    print('Waiting for state={0} for {1}'.format(desired_state, ec2_instance_ids))
    while not all_synced:
        response = ec2_client.describe_instance_status(InstanceIds=ec2_instance_ids)
        if len(response['InstanceStatuses']) > 0:
            processing = False
            for item in response['InstanceStatuses']:
                state = item['InstanceState']
                print(str(state))
                if state['Name'] != desired_state:
                    print('--> Y {0}: State={1}'.format(item['InstanceId'], state['Name']))
                    processing = True

            all_synced = (processing == False)
        else:
            all_synced = (desired_state == 'terminated')

        if not all_synced:
            time.sleep(10)


def create_ec2_instances(ec2_client):
    """
    Create EC2 instance(s) in the cluster
    For now I expect a default cluster to be there
    By default, your container instance launches into your default cluster.
    If you want to launch into your own cluster instead of the default,
    choose the Advanced Details list and paste the following script
    into the User data field, replacing your_cluster_name with the name of your cluster.
    !/bin/bash
    echo ECS_CLUSTER=your_cluster_name >> /etc/ecs/ecs.config
    """

    print("Starting EC2 Instances...")
    response = ec2_client.run_instances(
        # Use the official ECS image
        DryRun=False,
        ImageId=ECS_CONFIG['AMI'],
        MinCount=ECS_CONFIG['INSTANCE_MIN_COUNT'],
        MaxCount=ECS_CONFIG['INSTANCE_MAX_COUNT'],
        InstanceType=ECS_CONFIG['INSTANCE_TYPE'],
        IamInstanceProfile={
            "Name": ECS_CONFIG['INSTANCE_ROLE']
        },
        SecurityGroupIds=SECURITY_GROUPS,
        KeyName='admin-ssh-keys',
        UserData="#!/bin/bash \n echo ECS_CLUSTER=" + ECS_CONFIG['CLUSTER_NAME'] + " >> /etc/ecs/ecs.config"
    )
    instances = response['Instances']
    ec2_instance_ids = []
    for instance in instances:
        ec2_instance_ids.append(instance['InstanceId'])
    print('ec2 instances: {}'.format(ec2_instance_ids))

    wait_until_ec2_state_changes(ec2_client, ec2_instance_ids, u'running')

@task
def run_instances(ctx):
    """
    This task can be used to create new EC2 instances on the cluster
    Note that this task will create ECS_CONFIG['INSTANCE_MIN_COUNT'] NEW instances
    """
    ec2_client = boto3.client('ec2')
    create_ec2_instances(ec2_client)

@task
def create_ecs(ctx):
    """
    Creating an ECS deployment requires:
    1.- To create an ECS Cluster
    2.- To add EC2 instances to the cluster
    3.- To register all ECS Task Definitions (web, worker, etc,)
    4.- To create the ECS services to serve/manage the tasks

    If the cluster and EC2 instances are already running, skip 1 and 2
    """
    ecs_client = boto3.client('ecs')
    ec2_client = boto3.client('ec2')
    try:
        # 1.- Check if cluster exists, and create if needed
        # -------------------------------------------------
        print('Check if Cluster exists already...')
        response = ecs_client.describe_clusters(
            clusters=[
                ECS_CONFIG['CLUSTER_NAME'],
            ]
        )
        clusters = response['clusters']
        if len(clusters):
            print('Cluster already exist')
            for cluster in clusters:
                print('Found Cluster {clusterName} with:'.format(**cluster))
                print('                    {registeredContainerInstancesCount} instances'.format(**cluster))
                print('                    {runningTasksCount} running tasks'.format(**cluster))
                print('                    {activeServicesCount} services'.format(**cluster))

        else:
            print("Creating ECS Cluster...")
            response = ecs_client.create_cluster(clusterName=ECS_CONFIG['CLUSTER_NAME'])
            pprint.pprint(response['cluster'])

        # 2.- Create EC2 instances if needed
        # ----------------------------------
        print('Check if EC2 instances running in Cluster...')
        response = ecs_client.list_container_instances(cluster=ECS_CONFIG['CLUSTER_NAME'])
        pprint.pprint((response))
        if 'containerInstanceArns' in response and len(response['containerInstanceArns']):
            for ecs_container_inst in response['containerInstanceArns']:
                pprint.pprint((ecs_container_inst))
        else:
            create_ec2_instances(ec2_client)

        # 3.- Create ECS Tasks if needed
        # ------------------------------
        register_sqs_worker_tasks(ecs_client, ECS_CONFIG['TASK_FORMAT'].format(ECS_CONFIG['WORKER_NAME']))

        # 4.- Create ECS Services
        # -----------------------
        # Create service with exactly 1 desired instance of the task
        # Info: Amazon ECS allows you to run and maintain a specified number
        # (the "desired count") of instances of a task definition
        # simultaneously in an ECS cluster.

        response = ecs_client.create_service(
            cluster=ECS_CONFIG['CLUSTER_NAME'],
            serviceName=ECS_CONFIG['SERVICE_FORMAT'].format(ECS_CONFIG['WORKER_NAME']),
            taskDefinition=ECS_CONFIG['TASK_FORMAT'].format(ECS_CONFIG['WORKER_NAME']),
            desiredCount=ECS_CONFIG['WORKERS_COUNT'],
            deploymentConfiguration={
                'maximumPercent': 200,
                'minimumHealthyPercent': 50
            }
        )

        pprint.pprint(response)


    except ClientError as e:
        print(str(e))
        sys.exit()

@task
def update_ecs(ctx, count=ECS_CONFIG['WORKERS_COUNT']):
    """
    Deploy new code base:
    1.- Upload new image to ECR
    2.- Update Service
    """
    ecs_client = boto3.client('ecs')

    try:
        register_sqs_worker_tasks(ecs_client, ECS_CONFIG['TASK_FORMAT'].format(ECS_CONFIG['WORKER_NAME']))
        response = ecs_client.update_service(
            cluster=ECS_CONFIG['CLUSTER_NAME'],
            service=ECS_CONFIG['SERVICE_FORMAT'].format(ECS_CONFIG['WORKER_NAME']),
            taskDefinition=ECS_CONFIG['TASK_FORMAT'].format(ECS_CONFIG['WORKER_NAME']),
            desiredCount=count,
            deploymentConfiguration={
                'maximumPercent': 200,
                'minimumHealthyPercent': 50
            },
            forceNewDeployment=True,
        )
        pprint.pprint(response)
    except ClientError as e:
        print(str(e))
        sys.exit()


@task
def terminate_ecs(ctx):
    """
    Terminating an ECS deployment requires:
    1.- Update ECS services to desired count=0
    2.- Terminate EC2 instances
    3.- Deregister any ECS Tasks
    4.- Delete ECS Services
    5.- Delete the ECS cluster itself
    """
    ecs_client = boto3.client('ecs')
    ec2_client = boto3.client('ec2')
    try:
        print('Check if Cluster exists already...')
        response = ecs_client.describe_clusters(
            clusters=[
                ECS_CONFIG['CLUSTER_NAME'],
            ]
        )
        clusters = response['clusters']
        if len(clusters):
            for cluster in clusters:
                print('Terminating Cluster {clusterName} with:'.format(**cluster))
                print('                    {registeredContainerInstancesCount} instances'.format(**cluster))
                print('                    {runningTasksCount} running tasks'.format(**cluster))
                print('                    {activeServicesCount} services'.format(**cluster))

                # -------------------------------
                # Terminate Services
                try:
                    # Set desired service count to 0 (obligatory to delete)
                    response = ecs_client.update_service(
                        cluster=ECS_CONFIG['CLUSTER_NAME'],
                        service=ECS_CONFIG['SERVICE_FORMAT'].format(ECS_CONFIG['WORKER_NAME']),
                        desiredCount=0
                    )
                    # Delete service
                    response = ecs_client.delete_service(
                        cluster=ECS_CONFIG['CLUSTER_NAME'],
                        service=ECS_CONFIG['SERVICE_FORMAT'].format(ECS_CONFIG['WORKER_NAME'])
                    )
                    pprint.pprint(response)
                except:
                    print("Service not found/not active")

                # -------------------------------
                # De-register Tasks

                # List all task definitions and revisions
                response = ecs_client.list_task_definitions(
                    familyPrefix=ECS_CONFIG['TASK_FORMAT'].format(ECS_CONFIG['WORKER_NAME']),
                    status='ACTIVE'
                )

                # De-Register all task definitions
                for task_definition in response["taskDefinitionArns"]:
                    # De-register task definition(s)
                    deregister_response = ecs_client.deregister_task_definition(
                        taskDefinition=task_definition
                    )
                    pprint.pprint(deregister_response)

                # -------------------------------
                # Terminate all ECS EC2 instances
                print('Check if EC2 instances running in Cluster...')
                response = ecs_client.list_container_instances(cluster=ECS_CONFIG['CLUSTER_NAME'])
                if 'containerInstanceArns' in response and len(response['containerInstanceArns']):
                    container_instance_resp = ecs_client.describe_container_instances(
                        cluster=ECS_CONFIG['CLUSTER_NAME'],
                        containerInstances=response['containerInstanceArns']
                    )

                    for ec2_instance in container_instance_resp["containerInstances"]:
                        ec2_termination_resp = ec2_client.terminate_instances(
                            DryRun=False,
                            InstanceIds=[
                                ec2_instance["ec2InstanceId"],
                            ]
                        )

                else:
                    print('No running instances found')

                # -------------------------------
                # Deleting Cluster
                print('Leaving Cluster object')
                """
                print('Delete Cluster...')
                response = ecs_client.delete_cluster(cluster=ECS_CONFIG['CLUSTER_NAME'])
                pprint.pprint(response)
                """


    except ClientError as e:
        print(str(e))
        sys.exit()


@task
def describe_ecs(ctx):
    """
    Report summary of ECS resources:
    1.- ECS Cluster
    2.- EC2 Instances
    3.- ECS Tasks
    4.- ECS Services
    """
    ecs_client = boto3.client('ecs')
    ec2_client = boto3.client('ec2')
    try:
        response = ecs_client.describe_clusters(
            clusters=[
                ECS_CONFIG['CLUSTER_NAME'],
            ]
        )
        clusters = response['clusters']
        if len(clusters):
            for cluster in clusters:
                print('Found {status} Cluster {clusterName} with:'.format(**cluster))
                print('                    {registeredContainerInstancesCount} instances'.format(**cluster))
                print('                    {runningTasksCount} running tasks'.format(**cluster))
                print('                    {activeServicesCount} services'.format(**cluster))

                response = ecs_client.list_container_instances(cluster=ECS_CONFIG['CLUSTER_NAME'])
                if 'containerInstanceArns' in response and len(response['containerInstanceArns']):
                    response = ecs_client.describe_container_instances(
                        cluster=ECS_CONFIG['CLUSTER_NAME'],
                        containerInstances=response['containerInstanceArns']
                    )
                    ec2_instance_ids = []
                    for item in response['containerInstances']:
                        ec2_instance_id = item['ec2InstanceId']
                        ec2_instance_ids.append(ec2_instance_id)

                else:
                    print('No running instances found')



    except ClientError as e:
        print(str(e))
        sys.exit()


@task
def shutdown_ecs_workers(ctx):
    """
    List runnining tasks
    """
    payload = {
        'module': 'apps.sqsworker.worker',
        'class': 'WorkerShutDownAction',
        'arguments': {
            'timestamp': datetime.datetime.utcnow().isoformat()
        }
    }

    ecs_client = boto3.client('ecs')
    sqs = boto3.resource('sqs', region_name=AWS_REGION)

    try:
        sqs_queue = sqs.get_queue_by_name(QueueName=SQS_WORKER_QUEUE_NAME)
    except Exception as e:
        print("Fail to get SQS queue {}. Error: {}".format(SQS_WORKER_QUEUE_NAME, str(e)))
        raise e

    try:
        response = ecs_client.list_tasks(
            cluster=ECS_CONFIG['CLUSTER_NAME'],
            family=ECS_CONFIG['TASK_FORMAT'].format(ECS_CONFIG['WORKER_NAME']),
        )
        response = ecs_client.describe_tasks(
            cluster=ECS_CONFIG['CLUSTER_NAME'],
            tasks=response['taskArns']
        )
        group = 'service:{}'.format(ECS_CONFIG['SERVICE_FORMAT'].format(ECS_CONFIG['WORKER_NAME']))
        for task in response['tasks']:
            if task['group'] == group and task['lastStatus'] == 'RUNNING':
                print('Shutting down Worker: {}'.format(task['taskArn']))
                response = sqs_queue.send_message(MessageBody=json.dumps(payload))
                print('Message sent - Message ID: {0}'.format(response.get('MessageId')))

    except ClientError as e:
        print(str(e))
        sys.exit()


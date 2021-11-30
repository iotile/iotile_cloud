import configparser
import os

from invoke import task

from ecs.tasks import *

config = configparser.ConfigParser()
config.read('.ini')


AWS_PROFILE = 'iotile_cloud'
AWS_REGION = 'us-east-1'
# See .ini.sample for example of expected .ini
AWS_ACCOUNT = config['DEFAULT']['AWS_ACCOUNT']

DEFAULT_SERVER_APP_NAME = 'iotile-cloud-foss'
DEFAULT_SERVER_ENV_NAME = 'iotile-cloud-foss'

PROFILE_OPT = '--profile {profile}'.format(profile=AWS_PROFILE)
REGION_OPT = '--region {region}'.format(region=AWS_REGION)

# SERVER_AMI = '64bit Amazon Linux 2 v3.1.1 running Python 3.7'
SERVER_AMI = '64bit Amazon Linux 2018.03 v2.10.6 running Python 3.6'

SERVER_INSTANCE_TYPE = 't2.medium'

CDN_STATICS_DISTRIBUTION_ID = 'xxxxxxx'

# SecurityGroup='iotile-group' with ingress on port 6379 and source from itself
# .ebextensions/02_ec2.config should have:
#   - namespace: aws:autoscaling:launchconfiguration
#   option_name: SecurityGroups
#   value: 'iotile-group'

SECURITY_GROUP = 'sg-xxxxxx'  # Use task create_security_groups() if you need to create new

DB_CONFIG = {
    'SECURITY_GROUP': SECURITY_GROUP,
    # Set RDS_HOTSNAME = iotile-db1.c6n1a15tvye6.us-east-1.rds.amazonaws.com
    'DB_ID': 'iotile-cloud-db1',
    'DB_NAME': 'iotiledb1',
    'DB_VERSION': '9.6',
    'DB_TYPE': 'postgres',
    'DB_USER': config['DEFAULT']['DB_USERNAME'],
    'DB_PASSWORD': config['DEFAULT']['DB_PASSWORD'],
    'DB_INSTANCE_TYPE': 'db.m4.large',
    'DB_STORAGE': 20,
    'DB_IOPS': 1000  # Not used
}


CACHE_CONFIG = {
    'SECURITY_GROUP': SECURITY_GROUP,
    'REDIS_ID': 'iotile-cloud-redis1',
    'REDIS_NUM_NODES': 1,
    'REDIS_INSTANCE_TYPE': 'cache.t2.small',
    'REDIS_VERSION': '2.8.24',
    'REDIS_PORT': 6379,
    'NOTIFICATION': 'arn:aws:sns:us-east-1:{0}:IOTileCloudEBNotifications'.format(AWS_ACCOUNT)

}

SG_CONFIG = {
    'NAME': 'iotile-cloud-group1',
    'DESCRIPTION': 'Security Group for RDS and ElasticCache'
}

AWS_SERVER_TAGS = [{
    'Key': 'Project',
    'Value': 'IOTileCloud'
}, {
    'Key': 'IOTile',
    'Value': 'Production'
}]

DYNAMODB_CONFIG = {
    'iotile-devices': {
        'TABLE_NAME_FORMAT': 'iotile-devices-{stage}',
        'PRIMARY_READ_CAPACITY_UNITS': {
            'dev': 2,
            'stage': 2,
            'prod': 5
        },
        'PRIMARY_WRITE_CAPACITY_UNITS': {
            'dev': 1,
            'stage': 2,
            'prod': 5
        },
        'SECONDARY_READ_CAPACITY_UNITS': {
            'dev': 1,
            'stage': 1,
            'prod': 3
        },
        'SECONDARY_WRITE_CAPACITY_UNITS': {
            'dev': 1,
            'stage': 1,
            'prod': 2
        },
    }
}

@task
def build_statics(ctx, build=False):
    """Deploy static
    e.g.
       inv build-statics
    """
    cmd = 'sh build-webapp.sh'
    ctx.run(cmd, pty=True)

@task
def deploy_statics(ctx, build=False):
    """Deploy static
    e.g.
       inv deploy-statics
    """
    cmds = [
        f'aws s3 sync --profile iotile_cloud ./staticfiles/ s3://iotile-cloud-statics/static',
        f'aws cloudfront --profile iotile_cloud create-invalidation --distribution-id {CDN_STATICS_DISTRIBUTION_ID} --paths /',
    ]

    for cmd in cmds:
        ctx.run(cmd, pty=True)


@task
def init(ctx, type='server'):

    os.chdir(type)
    cmd = 'eb init -p "{ami}" {region} {profile} {name}'.format(region=REGION_OPT,
                                                                ami=SERVER_AMI,
                                                                profile=PROFILE_OPT,
                                                                name=DEFAULT_SERVER_APP_NAME)
    ctx.run(cmd, pty=True)
    os.chdir('..')


@task
def build_docker(ctx):
    """
    Assumes we have logged in to AWS ECR using the command you get with

    aws ecr get-login --region us-east-1

    """
    for image in ['server']:
        os.chdir(image)
        ctx.run('sh tag_image.sh', pty=True)
        os.chdir('..')


@task
def deploy_worker(ctx, count=ECS_CONFIG['WORKERS_COUNT']):
    """
    Build Docker image and upload to ECR
    Update ECS Task/Service
    """
    build_docker(ctx)

    update_ecs(ctx, count)


@task
def create(ctx, type='server'):

    init(ctx, type)

    # deploy_statics(ctx, True)

    os.chdir(type)

    # basic = '--timeout 30 --instance_type t2.micro --service-role aws-elasticbeanstalk-service-role'
    basic = '--timeout 30 --instance_type {0}'.format(SERVER_INSTANCE_TYPE)
    '''
    EB_DB_CMD = '-db -db.i {dbi} -db.engine {t} -db.version {v} -db.user {u} -db.pass {p}'.format(
       dbi=DB_CONFIG['DB_INSTANCE_TYPE'], t=DB_CONFIG['DB_TYPE'],
       v=DB_CONFIG['DB_VERSION'], u=DB_CONFIG['DB_USER'], p=DB_CONFIG['DB_PASSWORD']
    )

    cmd = "eb create {basic} {db} {region} {profile} -c {cname} {name}".format(basic=basic,
                                                                               db=EB_DB_CMD,
                                                                               region=REGION_OPT,
                                                                               profile=PROFILE_OPT,
                                                                               cname=DEFAULT_SERVER_ENV_NAME,
                                                                               name=DEFAULT_SERVER_APP_NAME)
    '''
    cmd = "eb create {basic} {region} {profile} -c {cname} {name}".format(basic=basic,
                                                                          region=REGION_OPT,
                                                                          profile=PROFILE_OPT,
                                                                          cname=DEFAULT_SERVER_APP_NAME,
                                                                          name=DEFAULT_SERVER_ENV_NAME)

    ctx.run(cmd, pty=True)


@task
def deploy(ctx, type='server', skip_statics=False):

    if not skip_statics and type == 'server':
        # Just for Server, we need to deploy statics first
        # Will deploy everything under /staticfiles. If new
        # third party packages are added, a local python manage.py collectstatic
        # will have to be run to move static files for that package to /staticfiles
        deploy_statics(ctx, build=True)

    os.chdir(type)
    ctx.run('eb deploy --region={region} --timeout 25'.format(region=AWS_REGION), pty=True)

    # Deploy workers after server to ensure db migrations are done first
    os.chdir('..')
    deploy_worker(ctx, ECS_CONFIG['WORKERS_COUNT'])


@task
def deploy_lambdas(ctx):
    lambda_dirnames = [
        'streamDataProcessing',  # MQTT Processing Function (to write to dynamodb)
    ]

    os.chdir('lambdas')
    for lambda_dirname in lambda_dirnames:
        os.chdir(lambda_dirname)
        ctx.run('node-lambda deploy', pty=True)
        os.chdir('..')


@task
def report_rds_instance(ctx, all=False):
    print('**** report_rds_instance ****')
    rds = boto3.client('rds')

    running = True
    while running:
        response = rds.describe_db_instances()

        db_instances = response['DBInstances']

        for db_instance in db_instances:
            # pprint.pprint(db_instance)

            interesting_data = [
                'DBInstanceIdentifier', 'DBInstanceClass', 'Engine', 'EngineVersion',
                'DBName', 'MasterUsername',
                'AllocatedStorage', 'MultiAZ', 'StorageEncrypted', 'StorageType'
            ]
            for key in interesting_data:
                print('{0:<20} = {1}'.format(key, db_instance[key]))
            print('')

            status = db_instance['DBInstanceStatus']

            print('Last DB status: {0}'.format(status))

            if status == 'available':
                endpoint = db_instance['Endpoint']
                host = endpoint['Address']
                # port = endpoint['Port']

                print('DB instance ready with host: {}'.format(host))
                running = False
                print('----------------')
            else:
                time.sleep(10)


@task
def report_redis_cluster(ctx, all=False):
    print('**** report_redis_cluster ****')
    redis = boto3.client('elasticache')

    response = redis.describe_cache_clusters()
    # pprint.pprint(response)

    clusters = response['CacheClusters']
    for cluster in clusters:
        interesting_data = [
            'CacheClusterId', 'CacheClusterStatus', 'CacheNodeType', 'NumCacheNodes',
            'Engine', 'EngineVersion',
        ]
        for key in interesting_data:
            print('{0:<20} = {1}'.format(key, cluster[key]))
        print('')

        groups = redis.describe_replication_groups()
        if len(groups['ReplicationGroups']):
            pprint.pprint(groups['ReplicationGroups'])

    print('----------------')


@task
def create_rds_instance(ctx):
    rds = boto3.client('rds')
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=DB_CONFIG['DB_ID'],
            AllocatedStorage=DB_CONFIG['DB_STORAGE'],
            DBName=DB_CONFIG['DB_NAME'],
            Engine=DB_CONFIG['DB_TYPE'],
            EngineVersion=DB_CONFIG['DB_VERSION'],
            AutoMinorVersionUpgrade=True,
            # General purpose SSD
            StorageType='gp2',  # TODO: Is this ok?
            StorageEncrypted=False,  # TODO: Change to True for Production
            MultiAZ=True,
            MasterUsername=DB_CONFIG['DB_USER'],
            MasterUserPassword=DB_CONFIG['DB_PASSWORD'],
            VpcSecurityGroupIds=[DB_CONFIG['SECURITY_GROUP'], ],
            DBInstanceClass=DB_CONFIG['DB_INSTANCE_TYPE'],
            Tags=AWS_SERVER_TAGS
        )
        print('Starting RDS instance with ID: {0}'.format(DB_CONFIG['DB_ID']))
    except ClientError as e:
        print(str(e))
        if e and 'DBInstanceAlreadyExists' in e.message:
            print('DB instance {0} exists already, continuing to poll ...'.format(DB_CONFIG['DB_ID']))
        else:
            raise
        sys.exit()

    report_rds_instance(ctx)


@task
def create_redis_cluster(ctx):
    redis = boto3.client('elasticache')
    try:
        # TODO: Change for production: 'cross-az'
        response = redis.create_cache_cluster(
            CacheClusterId=CACHE_CONFIG['REDIS_ID'],
            AZMode='single-az',
            NumCacheNodes=CACHE_CONFIG['REDIS_NUM_NODES'],
            CacheNodeType=CACHE_CONFIG['REDIS_INSTANCE_TYPE'],
            Engine='redis',
            EngineVersion=CACHE_CONFIG['REDIS_VERSION'],
            SecurityGroupIds=[CACHE_CONFIG['SECURITY_GROUP'], ],
            Tags=AWS_SERVER_TAGS,
            Port=CACHE_CONFIG['REDIS_PORT'],
            NotificationTopicArn=CACHE_CONFIG['NOTIFICATION'],
            AutoMinorVersionUpgrade=True
        )
        print('Starting Redis instance with ID: {0}'.format(CACHE_CONFIG['REDIS_ID']))
    except ClientError as e:
        print(str(e))
        sys.exit()

    report_redis_cluster(ctx)


@task
def create_security_groups(ctx):
    ec2 = boto3.resource('ec2')
    try:
        mysg = ec2.create_security_group(
            GroupName=SG_CONFIG['NAME'],
            Description=SG_CONFIG['DESCRIPTION']
        )
        sg_id = mysg.group_id
        print('Created Security Group: {0} ({1})'.format(SG_CONFIG['NAME'], sg_id))

        # RDS Ingress
        mysg.authorize_ingress(
            IpProtocol="tcp",
            CidrIp="0.0.0.0/0",
            FromPort=5432,
            ToPort=5432
        )
        print('-> Added RDS Ingress(5432)')

        # ElasticCache Ingress
        mysg.authorize_ingress(
            IpProtocol="tcp",
            CidrIp="0.0.0.0/0",
            FromPort=6379,
            ToPort=6379
        )
        print('-> Added ElasticCache Ingress (6379)')

        # Redshift Ingress
        mysg.authorize_ingress(
            IpProtocol="tcp",
            CidrIp="0.0.0.0/0",
            FromPort=5439,
            ToPort=5439
        )
        print('-> Added Redshift Ingress (5439)')

        mysg.create_tags(Tags=AWS_SERVER_TAGS)
        print('-> Added Tags')

        print('==============================================')
        print('Set All SECURITY_GROUP constants to {0}'.format(sg_id))
        print('==============================================')

    except ClientError as e:
        print(str(e))
        sys.exit()


@task
def describe_lambdas(ctx):
    client = boto3.client('lambda')
    response = client.get_function(
        FunctionName='arn:aws:lambda:us-east-1:{0}:function:sl-pipeline-dev-main'.format(AWS_ACCOUNT)
    )
    print('=============================')
    pprint.pprint(response)
    response = client.list_event_source_mappings(
        FunctionName='arn:aws:lambda:us-east-1:{0}:function:sl-pipeline-dev-main'.format(AWS_ACCOUNT)
    )
    print('=============================')
    pprint.pprint(response)
    response = client.get_event_source_mapping(
        UUID='a8d9e806-be0b-4ebe-8c75-9519a939f8a4'
    )
    print('=============================')
    pprint.pprint(response)


@task
def create_dynamodb_device_table(ctx, stage='dev'):
    config = DYNAMODB_CONFIG['iotile-devices']
    table_name = config['TABLE_NAME_FORMAT'].format(stage=stage)
    dynamodb = boto3.resource('dynamodb')

    try:
        # Create the DynamoDB table.
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'device_slug',
                    'KeyType': 'HASH'
                },
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'project_uuid',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'device_slug',
                    'AttributeType': 'S'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': config['PRIMARY_READ_CAPACITY_UNITS'][stage],
                'WriteCapacityUnits': config['PRIMARY_WRITE_CAPACITY_UNITS'][stage]
            },
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'project-uuid-index',
                    'KeySchema': [
                        {
                            'AttributeName': 'project_uuid',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'device_slug',
                            'KeyType': 'RANGE'
                        },
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    },
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': config['SECONDARY_READ_CAPACITY_UNITS'][stage],
                        'WriteCapacityUnits': config['SECONDARY_WRITE_CAPACITY_UNITS'][stage]
                    }
                },
            ]
        )
    except ClientError as e:
        error_code = e.response['Error'].get('Code', 'Unknown')

        # If table exists, do not fail, just return the description.
        if error_code == 'ResourceInUseException':
            print('Table {} already exists'.format(table_name))
            sys.exit()
        else:
            raise e

    # Wait until the table exists.
    print('Waiting for table to be created...')
    table.meta.client.get_waiter('table_exists').wait(TableName=table_name)

    # Print out some data about the table.
    print(table.item_count)


@task
def delete_dynamodb_device_table(ctx, stage='dev'):
    config = DYNAMODB_CONFIG['iotile-devices']
    table_name = config['TABLE_NAME_FORMAT'].format(stage=stage)
    dynamodb = boto3.resource('dynamodb')

    table = dynamodb.Table(table_name)
    try:
        count = table.item_count
    except ClientError as e:
        error_code = e.response['Error'].get('Code', 'Unknown')
        if error_code == 'ResourceNotFoundException':
            print('Table {} does not exists'.format(table_name))
            sys.exit()
        else:
            raise e

    print('-------------------------------------------------------------------')
    print('DANGER: You are about to delete an un-backed-up database')
    print('        Table has {} items'.format(count))
    print('        Type table name ({}) to confirm'.format(table_name))
    choice = input('> ')
    print('-------------------------------------------------------------------')
    if choice != table_name:
        print('-> Nothing done')
        sys.exit()

    try:
        print('Deleting {0}'.format(choice))
        table.delete()
        print('Dynamodb Table {} deleted'.format(table_name))
    except ClientError as e:
        print('Unable to delete')
        print(str(e))


@task
def update_secret_key(ctx, name, value):
    key = 'arn:aws:kms:us-east-1:xxxxxxxxxxxxxx:key/20cba84a-898d-4d97-a3f8-c1c68ad6dc01'
    cmd = 'aws ssm put-parameter --name {}'.format(name)
    cmd += ' --value "{}"'.format(value)
    cmd += ' --type SecureString --key-id "{}"'.format(key)
    cmd += ' --region {}'.format(AWS_REGION)
    print(cmd)
    # ctx.run(cmd, pty=True)


@task
def create_secret_key(ctx):
    for key in config['SECRETS']:
        value = config['SECRETS'][key]
        update_secret_key(ctx, key, value)


@task
def test(ctx, action='custom', path='./apps/'):
    """Full unit test and test coverage.
    Includes all django management funcions to setup databases
    (See runtest.sh)
    Args:
        action (string): One of
            - signoff: To run full/default runtest.sh
            - custom: To run a specific set of tests
            - stop: to stop all containters
            - down: to bring down (kill) all containers (and dbs)
        path (strin): If custom, path indicatest the test path to run
    e.g.
        inv test -a signoff       # To run full default signoff test
        inv test -p ./apps/report # to run Report tests
        inv test -a stop          # To stop all containers
        inv test -a down          # To kill all containers
    """
    # 2 Scale up or down
    cmd = 'docker-compose -f docker-compose.utest.yml -p iotile_cloud_test'
    if action == 'signoff':
        cmd += '  run --rm web'
    elif action == 'custom':
        cmd += f'  run --rm web py.test -s {path}'
    elif action in ['stop', 'down', 'build',]:
        cmd += f' {action}'
    elif 'migrate' in action:
        cmd += ' run --rm web python manage.py migrate'
    else:
        print('action can only be signoff/custom/build/stop/down/migrate')
    ctx.run(cmd, pty=True)

@task
def run_local(ctx, action='up'):
    """To run local server
    Args:
        action (string): One of
            - up: To run docker-compose up
            - stop: to stop all containters
            - down: to bring down (kill) all containers (and dbs)
            - logs-<name>: to show logs where <name> is server, worker1, worker2, etc.
    e.g.
        inv run-local -a up             # To run docker-compose up -d
        inv run-local -a stop           # To run docker-compose stop
        inv run-local -a down           # To run docker-compose down
        inv run-local -a logs-server    # To show logs for Server
        inv run-local -a makemigrations # Run Django makemigrations
        inv run-local -a collectstatic  # Run Django collectstatic 
    """
    # 2 Scale up or down
    cmd = 'docker-compose -f docker-compose.yml -p iotile_cloud'
    if action == 'up':
        cmd += '  up -d'
    elif action in ['stop', 'down', 'build']:
        cmd += f' {action}'
    elif 'logs' in action:
        parts = action.split('-')
        assert len(parts) == 2
        cmd += ' logs {}'.format(parts[1])
    elif 'makemigrations' in action:
        cmd += ' run --rm web python manage.py makemigrations'
    elif 'collectstatic' in action:
        cmd += ' run --rm web python manage.py collectstatic --noinput'
    elif 'migrate' in action:
        cmd += ' run --rm web python manage.py migrate'
    else:
        print('action can only be up/stop/down')
    ctx.run(cmd, pty=True)

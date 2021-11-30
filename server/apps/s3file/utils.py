import os

from django.conf import settings

from apps.utils.aws.s3 import get_s3_post_url


def get_content_type(key):
    """
    Try to guess what Content-Type is required based on the file extension
    :param ext: a string of type '.ext'
    :return: Content-Type as a string
    """
    base, ext = os.path.splitext(key)
    type = 'text/plain'
    if ext:
        factory = {
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.html': 'text/html',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.zip': 'application/zip',
            '.js': 'application/javascript',
            '.jsonp': 'application/javascript',
            '.json': 'application/json',
            '.xls': 'application/octet-stream',
        }
        type = factory.get(ext.lower(), type)
    return type


def get_s3file_post_url(key_name, max_length, obj_uuid, type, acl='private', bucket=settings.S3FILE_BUCKET_NAME, content_type=None):
    if not content_type:
        # If no content type is passed, guess one based on extension
        content_type = get_content_type(key_name)

    fields = {
        'acl': acl,
        'x-amz-meta-filename': os.path.basename(key_name),
        'x-amz-meta-uuid': str(obj_uuid),
        'x-amz-meta-type': type,
        'Content-Type': content_type,
    }

    post = get_s3_post_url(
        bucket_name=bucket,
        key_name=key_name,
        fields=fields,
        max_length=max_length
    )

    return post

from rest_framework_api_key.permissions import KeyParser

from apps.org.models import AuthAPIKey


# Get AuthAPIKey from a given generated key
#   To be used to retrieve the org slug from the request
#   TODO: move this functionality to a custom AuthAPIKeyManager class
def get_apikey_object_from_generated_key(key):
    if not key or not AuthAPIKey.objects.is_valid(key):
        return None
    apikey_prefix, _, _ = key.partition(".")

    try:
        actualKey = AuthAPIKey.objects.get(id__startswith=apikey_prefix, revoked=False)
    except AuthAPIKey.DoesNotExist:
        return None
    return actualKey


# Get org slug from a request with AuthAPIKey
def get_org_slug_from_apikey(request):
    apikey = KeyParser().get(request)
    actualKey = get_apikey_object_from_generated_key(apikey)
    if actualKey is None:
        return None
    return actualKey.org.slug

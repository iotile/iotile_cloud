from uuid import UUID

def validate_uuid(uuid_string):
    try:
        val = UUID(uuid_string, version=4)
        return True
    except ValueError:
        # If it's a value error, then the string
        # is not a valid hex code for a UUID.
        return False


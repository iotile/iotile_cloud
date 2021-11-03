from .production import *  # Import from your main/production settings.

# Override the elasticsearch configuration and provide a custom timeout
ELASTICSEARCH_DSL['default']['timeout'] = 120
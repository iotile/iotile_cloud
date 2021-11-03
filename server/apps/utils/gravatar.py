# import code for encoding urls and generating md5 hashes
try:
    # Python 3.4
    import urllib.parse
except ImportError:
    # Python 2.7
    import urllib
import hashlib


def get_gravatar_thumbnail_url(email, size=28):
    # Set your variables here
    default = 'identicon'

    # construct the url
    gravatar_url = "https://secure.gravatar.com/avatar/" + hashlib.md5(email.lower().encode('utf-8')).hexdigest() + "?"
    try:
        # Python 3.4
        gravatar_url += urllib.parse.urlencode({'d': default, 's': str(size)})
    except:
        # Python 2.7
        gravatar_url += urllib.urlencode({'d': default, 's': str(size)})

    return gravatar_url
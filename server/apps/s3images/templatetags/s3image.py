from django import template
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def on_image_error():
    no_image = static('dist/webapp/app/images/no-image.thumbnail.jpg')

    err = """
       if (this.src != '{no_image}') this.src = '{no_image}';
    """.format(no_image=no_image)

    return err


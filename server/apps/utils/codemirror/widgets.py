from django import forms


class JsonEditor(forms.Textarea):
    def __init__(self, *args, **kwargs):
        super(JsonEditor, self).__init__(*args, **kwargs)
        self.attrs['class'] = 'json-editor'

    class Media:
        css = {
            'all': (
                'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.35.0/codemirror.min.css',
            )
        }
        js = (
            'https://ajax.googleapis.com/ajax/libs/jquery/1.9.1/jquery.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.35.0/codemirror.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.35.0/addon/mode/simple.js',
            'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.35.0/mode/javascript/javascript.min.js',
            # Changes to /webapp/src/app/scripts/codemirror.js will require this file name to be updated
            'https://cdn.iotile.cloud/static/dist/webapp/app/scripts/codemirror-5b01d78cf5.js',
        )


class SgfEditor(forms.Textarea):
    def __init__(self, *args, **kwargs):
        super(SgfEditor, self).__init__(*args, **kwargs)
        self.attrs['class'] = 'sgf-editor'

    class Media:
        css = {
            'all': (
                'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.35.0/codemirror.min.css',
            )
        }
        js = (
            'https://ajax.googleapis.com/ajax/libs/jquery/1.9.1/jquery.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.35.0/codemirror.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.35.0/addon/mode/simple.js',
            # Changes to /webapp/src/app/scripts/codemirror.js will require this file name to be updated
            'https://cdn.iotile.cloud/static/dist/webapp/app/scripts/codemirror-5b01d78cf5.js',
        )

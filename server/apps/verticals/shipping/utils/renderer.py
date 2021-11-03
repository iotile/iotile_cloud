import csv
from io import StringIO

from rest_framework.renderers import BaseRenderer


class OrgQualityCSVRenderer(BaseRenderer):
    """
    Renderer serializes the TripOrgQualityReport into CSV
    """

    media_type = 'text/csv'
    format = 'csv'
    level_sep = '.'
    header = None
    labels = None  # {'<field>':'<label>'}
    writer_opts = None

    def render(self, data, media_type=None, renderer_context=None):
        """
        Renders serialized *data* into CSV.
        """
        if data is None:
            return ''

        assert isinstance(data, dict)

        csvfile = StringIO()
        fieldnames = ['Device ID', 'Label']
        if 'property_keys' in data['config']:
            for col in data['config']['property_keys']:
                fieldnames.append(col )
        if 'summary_keys' in data['config']:
            for col in data['config']['summary_keys']:
                fieldnames.append(col)

        fieldnames_set = set()
        for item in fieldnames:
            fieldnames_set.add(item)

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in data['results']:
            row = {
                'Device ID': item['slug'],
                'Label': item['label']
            }
            for key in item['data']['summary'].keys():
                if key in fieldnames_set:
                    row[key] = item['data']['summary'][key]
            for key in item['data']['properties'].keys():
                if key in fieldnames_set:
                    row[key] = item['data']['properties'][key]
            writer.writerow(row)

        return csvfile.getvalue()


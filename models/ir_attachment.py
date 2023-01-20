import pathlib
import base64
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

def is_s3_bucket(bucket):
    meta = getattr(bucket, "meta", None)
    return meta and getattr(meta, "service_name", None) == "s3"


class IrAttachment(models.Model):

    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('type') != 'url':
                # convert Binary to Url
                values = self._check_contents(values)
                raw, datas = values.pop('raw', None), values.pop('datas', None)
                if raw or datas:
                    if isinstance(raw, str):
                        raw = raw.encode()

                bucket = self.get_s3_bucket()
                filename = values.get("name")
                mimetype = self._compute_mimetype(values)
                related_values = self._get_datas_related_values_with_bucket(bucket, raw or base64.b64decode(datas or b''), filename, mimetype)
                values['type'] = 'url'
                values['datas'] = False
                values['url'] = related_values['url']

        return super(IrAttachment, self).create(vals_list)

    def _get_datas_related_values_with_bucket(
            self, bucket, bin_data, filename, mimetype, checksum=None
    ):
        bin_data = bin_data if bin_data else b""
        if not checksum:
            checksum = self._compute_checksum(bin_data)
        fname, url = self._file_write_with_bucket(
            bucket, bin_data, filename, mimetype, checksum
        )
        return {
            "file_size": len(bin_data),
            "checksum": checksum,
            "index_content": self._index(bin_data, mimetype),
            "store_fname": fname,
            "db_datas": False,
            "type": "url",
            "url": url,
        }


    def get_s3_bucket(self):
        bucket = self.env["res.config.settings"].get_s3_bucket()
        return bucket

    def _file_write_with_bucket(self, bucket, bin_data, filename, mimetype, checksum):
        # make sure, that given bucket is s3 bucket
        if not is_s3_bucket(bucket):
            return super(IrAttachment, self)._file_write_with_bucket(
                bucket, bin_data, filename, mimetype, checksum
            )
        filename = checksum + pathlib.Path(filename).suffix
        file_id = "odoo-test/{}".format(filename)

        bucket.put_object(
            Key=file_id,
            Body=bin_data,
            ACL="public-read",
            ContentType=mimetype,
            ContentDisposition='attachment; filename="%s"' % filename,
        )

        _logger.debug("uploaded file with id {}".format(file_id))
        obj_url = self.env["res.config.settings"].get_s3_obj_url(bucket, file_id)
        return file_id, obj_url

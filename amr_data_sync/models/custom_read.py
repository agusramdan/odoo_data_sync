# -*- coding: utf-8 -*-
from collections import defaultdict

import requests
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import image_process
import json
import logging
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

from odoo.models import Model


# override method write di semua model
def custom_read(self, fields=None, load='_classic_read'):
    if self.env.context.get('__from_sync_data_api'):
        def valid_field(f):
            return not (f.compute is True)

        if fields is None:
            fields = self.check_field_access_rights('read', None)
        _fields = self._fields
        fields = [field_name for field_name in fields if valid_field(_fields[field_name])]

    return super(Model, self).read(fields=fields, load=load)


# patch method ke BaseModel
Model.read = custom_read

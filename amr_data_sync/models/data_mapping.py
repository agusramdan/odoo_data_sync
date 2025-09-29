# -*- coding: utf-8 -*-
from odoo import models, fields, api
import json
from datetime import datetime, date
from odoo.tools.safe_eval import safe_eval, test_python_expr

from ..tools.utils import *


class ExternalDataMapping(models.Model):
    _name = 'external.data.mapping'
    _description = 'Rule Mapping Synchronization'
    _order = 'sequence, id'
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If unchecked, it will allow you to hide the record without removing it."
    )
    sequence = fields.Integer(
        help="Priority of this mapping, the lower the number, the higher the priority to execute."
    )
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
        string='Mapping Strategy',
        required=True,
        ondelete='cascade'
    )
    name = fields.Char()
    description = fields.Text()
    internal_field = fields.Char()
    mapping_strategy = fields.Selection([
        ('field_mapping', 'Field Mapping'),
        ('constant', 'Constant'),
        ('function', "Function"),
        ('eval_script', "Eval"), ],
        string='Mapping Strategy', )
    key_name = fields.Char()
    function_name = fields.Char()
    eval_script = fields.Text()
    constant_value_type = fields.Selection([
        ('None', 'None'),
        ('False', 'False'),
        ('True', 'True'),
        ('empty_array', 'Empty Array'),
        ('empty_dict', 'Empty Dict'),
        ('empty_string', 'Empty String'),
        ('string', 'String'),
        ('integer', 'Integer'),
        ('float', 'Float'),
        ('boolean', 'Boolean'),
        ('date', 'Date'),
        ('datetime', 'Datetime')
    ], string='Constant Value Type', )

    constant_simple_value = fields.Boolean(compute='_compute_constant_simple_value')

    def _compute_constant_simple_value(self):
        for rec in self:
            if rec.constant_value_type in ['None', 'False', 'True', 'empty_array', 'empty_dict', 'empty_string']:
                rec.constant_simple_value = True
            else:
                rec.constant_simple_value = False

    constant_value = fields.Char()

    def mapping_data(self, external_data, model=None):
        if self.mapping_strategy == 'field_mapping':
            if self.key_name in external_data:
                return external_data[self.key_name]
            else:
                return None
        elif self.mapping_strategy == 'constant':
            if self.constant_value_type == 'None':
                return None
            elif self.constant_value_type == 'False':
                return False
            elif self.constant_value_type == 'True':
                return True
            elif self.constant_value_type == 'empty_array':
                return []
            elif self.constant_value_type == 'empty_dict':
                return {}
            elif self.constant_value_type == 'empty_string':
                return ''
            elif self.constant_value_type == 'string':
                return self.constant_value
            elif self.constant_value_type == 'integer':
                return int(self.constant_value)
            elif self.constant_value_type == 'float':
                return float(self.constant_value)
            elif self.constant_value_type == 'boolean':
                return bool(self.constant_value)
            elif self.constant_value_type == 'date':
                return datetime.strptime(self.constant_value, '%Y-%m-%d').date()
            elif self.constant_value_type == 'datetime':
                return datetime.strptime(self.constant_value, '%Y-%m-%d %H:%M:%S')
        elif self.mapping_strategy == 'function' and is_callable_method(model, self.function_name):
            func = getattr(model, self.function_name)
            if has_kwargs(func):
                return func(
                    external_data=external_data,
                    sync_strategy=self.sync_strategy_id,
                )
            else:
                return func()
        elif self.mapping_strategy == 'eval_script':
            try:
                eval_context = {'env': self.env, 'model': model,
                                'external_data': external_data,
                                'sync_strategy': self.sync_strategy_id
                                }
                safe_eval(self.eval_script.strip(), eval_context, mode="exec",
                          nocopy=True,
                          filename=str(self))  # nocopy allows to return 'value'
                return eval_context.get('value')
            except Exception as e:
                raise ValueError(f"Error evaluating script: {e}")
        else:
            raise ValueError("Invalid mapping strategy")

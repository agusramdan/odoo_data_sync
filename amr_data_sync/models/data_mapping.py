# -*- coding: utf-8 -*-

from odoo import models, fields, _
from datetime import datetime
from odoo.tools.safe_eval import safe_eval

from ..tools.utils import is_callable_method, has_kwargs


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
    relation_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
        string='Relation Strategy',
        ondelete='cascade'
    )
    name = fields.Char('Name')
    description = fields.Text()
    internal_field = fields.Char()
    mapping_strategy = fields.Selection([
        ('field_mapping', 'Field Mapping'),
        ('many2one', 'Many 2 One'),
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
    constant_value = fields.Char()

    def _compute_constant_simple_value(self):
        for rec in self:
            if rec.constant_value_type in ['None', 'False', 'True', 'empty_array', 'empty_dict', 'empty_string']:
                rec.constant_simple_value = True
            else:
                rec.constant_simple_value = False

    def mapping_data(self, external_data, model=None, parent_data_sync=None, field=None):

        if self.mapping_strategy == 'many2one':
            related_external_data_sync_id = self.env['external.data.sync'].get_or_create(
                external_data, self.relation_strategy_id
            )
            if related_external_data_sync_id:
                if related_external_data_sync_id.internal_odoo_id:
                    return related_external_data_sync_id.internal_odoo_id
                if parent_data_sync:
                    field_name = self.internal_field or self.key_name
                    related = parent_data_sync.related_ids.get_or_create(
                        related_external_data_sync_id, parent_data_sync, field_name, field_type='many2one',
                        required_before_create=field and field.required
                    )
                    if related:
                        return related.get_data_relation()
                return None
            return None

        elif self.mapping_strategy == 'field_mapping':
            key_name = self.key_name or self.internal_field
            if key_name in external_data:
                return external_data[key_name]
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
        elif self.mapping_strategy == 'function':
            if field.relational and field.comodel_name and field.comodel_name in self.env \
                    and is_callable_method(self.env[field.comodel_name], self.function_name):
                func = getattr(self.env[field.comodel_name], self.function_name)
            else:
                func = getattr(model, self.function_name)
            if has_kwargs(func):
                return func(
                    external_data=external_data,
                    sync_strategy=self.sync_strategy_id,
                )
            else:
                return func()
        elif self.mapping_strategy == 'eval_script':
            eval_script = self.eval_script and self.eval_script.strip()
            if not eval_script:
                return None
            try:
                eval_context = {'env': self.env,
                                'model': model,
                                'external_data': external_data,
                                'sync_strategy': self.sync_strategy_id,
                                'field': field
                                }
                safe_eval(eval_script, eval_context, mode="exec", nocopy=True)
                # nocopy allows to return 'value'
                return eval_context.get('value')
            except Exception as e:
                raise ValueError(f"Error evaluating script: {e}")
        else:
            raise ValueError("Invalid mapping strategy")

    def action_open_view(self):
        self.ensure_one()
        return {
            'name': _('Internal Data'),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
        }

from collections import defaultdict

from psycopg2._psycopg import AsIs
import inspect
from odoo import SUPERUSER_ID
from odoo.tools import clean_context, attrgetter

LOG_ACCESS_COLUMNS = ['create_uid', 'create_date', 'write_uid', 'write_date']


def insert_data_sql(self, vals_list):
    data_list = list()
    bad_names = {'parent_path'}
    if self._log_access:
        # the superuser can set log_access fields while loading registry
        if not (self.env.uid == SUPERUSER_ID and not self.pool.ready):
            bad_names.update(LOG_ACCESS_COLUMNS)
    data_list = []
    inversed_fields = set()

    for vals in vals_list:
        # add missing defaults
        vals = self._add_missing_default_values(vals)
        data = {}
        data['stored'] = stored = {}
        data['inversed'] = inversed = {}
        data['inherited'] = inherited = defaultdict(dict)
        data['protected'] = protected = set()
        for key, val in vals.items():
            if key in bad_names:
                continue
            field = self._fields.get(key)
            if not field:
                raise ValueError("Invalid field %r on model %r" % (key, self._name))
            if field.company_dependent:
                irprop_def = self.env['ir.property'].get(key, self._name)
                cached_def = field.convert_to_cache(irprop_def, self)
                cached_val = field.convert_to_cache(val, self)
                if cached_val == cached_def:
                    # val is the same as the default value defined in
                    # 'ir.property'; by design, 'ir.property' will not
                    # create entries specific to these records; skipping the
                    # field inverse saves 4 SQL queries
                    continue
            if field.store:
                stored[key] = val
            if field.inherited:
                inherited[field.related_field.model_name][key] = val
            elif field.inverse:
                inversed[key] = val
                inversed_fields.add(field)
            # protect non-readonly computed fields against (re)computation
            if field.compute and not field.readonly:
                protected.update(self._field_computed.get(field, [field]))

        data_list.append(data)

    return insert_sql(self, data_list)


def insert_sql(self, data_list):
    """ Create records from the stored field values in ``data_list``. """
    assert data_list
    cr = self.env.cr
    quote = '"{}"'.format

    # insert rows
    ids = []  # ids of created records
    other_fields = set()  # non-column fields
    translated_fields = set()  # translated fields

    # column names, formats and values (for common fields)
    columns0 = []
    if self._log_access:
        columns0.append(('create_uid', "%s", self._uid))
        columns0.append(('create_date', "%s", AsIs("(now() at time zone 'UTC')")))
        columns0.append(('write_uid', "%s", self._uid))
        columns0.append(('write_date', "%s", AsIs("(now() at time zone 'UTC')")))

    for data in data_list:
        # determine column values
        stored = data['stored']
        columns = [column for column in columns0 if column[0] not in stored]
        for name, val in sorted(stored.items()):
            field = self._fields[name]
            assert field.store

            if field.column_type:
                col_val = field.convert_to_column(val, self, stored)
                columns.append((name, field.column_format, col_val))
                if field.translate is True:
                    translated_fields.add(field)
            else:
                other_fields.add(field)

        # Insert rows one by one
        # - as records don't all specify the same columns, code building batch-insert query
        #   was very complex
        # - and the gains were low, so not worth spending so much complexity
        #
        # It also seems that we have to be careful with INSERTs in batch, because they have the
        # same problem as SELECTs:
        # If we inject a lot of data in a single query, we fall into pathological perfs in
        # terms of SQL parser and the execution of the query itself.
        # In SELECT queries, we inject max 1000 ids (integers) when we can, because we know
        # that this limit is well managed by PostgreSQL.
        # In INSERT queries, we inject integers (small) and larger data (TEXT blocks for
        # example).
        #
        # The problem then becomes: how to "estimate" the right size of the batch to have
        # good performance?
        #
        # This requires extensive testing, and it was prefered not to introduce INSERTs in
        # batch, to avoid regressions as much as possible.
        #
        # That said, we haven't closed the door completely.
        query = "INSERT INTO {} ({}) VALUES ({}) RETURNING id".format(
            quote(self._table),
            ", ".join(quote(name) for name, fmt, val in columns),
            ", ".join(fmt for name, fmt, val in columns),
        )
        params = [val for name, fmt, val in columns]
        cr.execute(query, params)
        ids.append(cr.fetchone()[0])

    # put the new records in cache, and update inverse fields, for many2one
    #
    # cachetoclear is an optimization to avoid modified()'s cost until other_fields are processed
    cachetoclear = []
    records = self.browse(ids)
    inverses_update = defaultdict(list)  # {(field, value): ids}
    for data, record in zip(data_list, records):
        data['record'] = record
        # DLE P104: test_inherit.py, test_50_search_one2many
        vals = dict({k: v for d in data['inherited'].values() for k, v in d.items()}, **data['stored'])
        set_vals = list(vals) + LOG_ACCESS_COLUMNS + [self.CONCURRENCY_CHECK_FIELD, 'id', 'parent_path']
        for field in self._fields.values():
            if field.type in ('one2many', 'many2many'):
                self.env.cache.set(record, field, ())
            elif field.related and not field.column_type:
                self.env.cache.set(record, field, field.convert_to_cache(None, record))
            # DLE P123: `test_adv_activity`, `test_message_assignation_inbox`, `test_message_log`, `test_create_mail_simple`, ...
            # Set `mail.message.parent_id` to False in cache so it doesn't do the useless SELECT when computing the modified of `child_ids`
            # in other words, if `parent_id` is not set, no other message `child_ids` are impacted.
            # + avoid the fetch of fields which are False. e.g. if a boolean field is not passed in vals and as no default set in the field attributes,
            # then we know it can be set to False in the cache in the case of a create.
            elif field.name not in set_vals and not field.compute:
                self.env.cache.set(record, field, field.convert_to_cache(None, record))
        for fname, value in vals.items():
            field = self._fields[fname]
            if field.type in ('one2many', 'many2many'):
                cachetoclear.append((record, field))
            else:
                cache_value = field.convert_to_cache(value, record)
                self.env.cache.set(record, field, cache_value)
                if field.type in ('many2one', 'many2one_reference') and record._field_inverses[field]:
                    inverses_update[(field, cache_value)].append(record.id)

    for (field, value), record_ids in inverses_update.items():
        field._update_inverses(self.browse(record_ids), value)

    # update parent_path
    records._parent_store_create()

    # protect fields being written against recomputation
    protected = [(data['protected'], data['record']) for data in data_list]
    with self.env.protecting(protected):
        # mark computed fields as todo
        records.modified(self._fields, create=True)

        if other_fields:
            # discard default values from context for other fields
            others = records.with_context(clean_context(self._context))
            for field in sorted(other_fields, key=attrgetter('_sequence')):
                field.create([
                    (other, data['stored'][field.name])
                    for other, data in zip(others, data_list)
                    if field.name in data['stored']
                ])

            # mark fields to recompute
            records.modified([field.name for field in other_fields], create=True)

        # if value in cache has not been updated by other_fields, remove it
        for record, field in cachetoclear:
            if self.env.cache.contains(record, field) and not self.env.cache.get(record, field):
                self.env.cache.remove(record, field)

    # check Python constraints for stored fields
    records._validate_fields(name for data in data_list for name in data['stored'])
    records.check_access_rule('create')

    # add translations
    if self.env.lang and self.env.lang != 'en_US':
        Translations = self.env['ir.translation']
        for field in translated_fields:
            tname = "%s,%s" % (field.model_name, field.name)
            for data in data_list:
                if field.name in data['stored']:
                    record = data['record']
                    val = data['stored'][field.name]
                    Translations._set_ids(tname, 'model', self.env.lang, record.ids, val, val)

    return records


def safe_call_method(obj, method_name, args=None, kwargs=None):
    """
    Memanggil method pada object secara aman.

    - method optional
    - method_name harus string
    - method harus callable
    - args disesuaikan dengan signature
    """

    if not obj or not method_name or not isinstance(method_name, str):
        return None

    if not hasattr(obj, method_name):
        raise AttributeError(f"Method {method_name} not found")

    method = getattr(obj, method_name, None)
    if not callable(method):
        raise AttributeError(f"Callable method '{method_name}' not found on {obj}")

    # === signature aware ===
    sig = inspect.signature(method)
    params = sig.parameters

    final_args = []
    final_kwargs = {}
    kwargs = kwargs or {}
    args = args or []
    for name, p in params.items():
        if p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD
        ):
            if args:
                final_args.append(args[0])
                args = args[1:]
            elif name in kwargs:
                final_args.append(kwargs[name])
            elif p.default is not inspect.Parameter.empty:
                pass
            else:
                raise TypeError(f"Missing required argument: {name}")

        elif p.kind == inspect.Parameter.VAR_POSITIONAL:
            final_args.extend(args)
            args = ()

        elif p.kind == inspect.Parameter.KEYWORD_ONLY:
            if name in kwargs:
                final_kwargs[name] = kwargs[name]
            elif p.default is inspect.Parameter.empty:
                raise TypeError(f"Missing keyword-only argument: {name}")

        elif p.kind == inspect.Parameter.VAR_KEYWORD:
            final_kwargs.update(kwargs)

    return method(*final_args, **final_kwargs)


def get_callable_method(obj, method):
    try:
        return hasattr(obj, method) and callable(getattr(obj, method))
    except Exception:
        return False


def is_callable_method(model, method):
    return get_callable_method(model, method)


def has_kwargs(func):
    sig = inspect.signature(func)
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


def convert_from_external_data(item):
    item_dict = {}
    if isinstance(item, int):
        item_dict['id'] = item
    elif isinstance(item, list):
        if len(item) > 0:
            item_dict['id'] = item[0]
        if len(item) > 1:
            item_dict['display_name'] = item[1]
    elif isinstance(item, dict):
        item_dict = item
    return item_dict

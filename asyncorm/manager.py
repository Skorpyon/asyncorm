from asyncpg.exceptions import UniqueViolationError

from .exceptions import QuerysetError, ModelError
from .fields import ManyToMany

__all__ = ['ModelManager', ]

MIDDLE_OPERATOR = {
    'gt': '>',
    'lt': '<',
    'gte': '>=',
    'lte': '<=',
}


class Queryset(object):
    db_manager = None
    orm = None

    def __init__(self, model):
        self.model = model
        self.query_chain = []
        self.table_name = self.model.table_name

    @classmethod
    def _set_orm(cls, orm):
        cls.orm = orm
        cls.db_manager = orm.db_manager

    # def _copy_me(self):
    #     queryset = Queryset()
    #     queryset.model = self.model
    #     return queryset

    def _creation_query(self):
        '''
        This is the creation query without the m2m_fields
        '''
        constraints = self._get_field_constraints()
        unique_together = self._get_unique_together()

        query = (
            'CREATE TABLE IF NOT EXISTS {table_name} '
            '({field_queries}{unique_together}); '
            '{constraints}'
        ).format(
            table_name=self.model.table_name,
            field_queries=self._get_field_queries(),
            unique_together=unique_together,
            constraints=constraints and constraints + ';' or '',
        )
        return query

    def _get_field_queries(self):
        # builds the table with all its fields definition
        return ', '.join(
            [f._creation_query() for f in self.model.fields.values()
             if not isinstance(f, ManyToMany)
             ]
        )

    def _get_field_constraints(self):
        # builds the table with all its fields definition
        return '; '.join(
            [f._field_constraints() for f in self.model.fields.values()]
        )

    def _get_unique_together(self):
        # builds the table with all its fields definition
        unique_string = ', UNIQUE ({}) '.format(
            ','.join(self.model._unique_together)
        )
        return self.model._unique_together and unique_string or ''

    def _get_m2m_field_queries(self):
        # builds the relational many to many table
        return '; '.join(
            [f._creation_query() for f in self.model.fields.values()
             if isinstance(f, ManyToMany)
             ]
        )

    def _model_constructor(self, record, instance=None):
        if not instance:
            instance = self.model()

        data = {}
        for k, v in record.items():
            data.update({k: v})

        instance._construct(data)
        return instance

    async def queryset(self):
        return await self.all()

    async def all(self):
        db_request = {
            'select': '*',
            'table_name': self.model.table_name,
            'action': 'db__select_all',
        }

        request = await self.db_manager.request(db_request)
        return [self._model_constructor(r) for r in request]

    async def count(self):
        db_request = {
            'select': '*',
            'table_name': self.model.table_name,
            'action': 'db__count',
        }

        return await self.db_manager.request(db_request)

    async def get(self, **kwargs):
        data = await self.filter(**kwargs)
        length = len(data)
        if length:
            if length > 1:
                raise QuerysetError(
                    'More than one {} where returned, there are {}!'.format(
                        self.model.__name__,
                        length,
                    )
                )

            return data[0]
        raise QuerysetError(
            'That {} does not exist'.format(self.model.__name__)
        )

    def calc_filters(self, kwargs, exclude=False):
        # recompose the filters
        bool_string = exclude and 'NOT ' or ''
        filters = []

        # if the queryset is a real model_queryset
        if self.model:
            for k, v in kwargs.items():
                # we format the key, the conditional and the value
                middle = '='
                if len(k.split('__')) > 1:
                    k, middle = k.split('__')
                    middle = MIDDLE_OPERATOR[middle]

                field = getattr(self.model, k)

                if middle == '=' and isinstance(v, tuple):
                    if len(v) != 2:
                        raise QuerysetError(
                            'Not a correct tuple definition, filter '
                            'only allows tuples of size 2'
                        )
                    filters.append(
                        bool_string +
                        '({k}>{min} AND {k}<{max})'.format(
                            k=k,
                            min=field._sanitize_data(v[0]),
                            max=field._sanitize_data(v[1]),
                        )
                    )
                else:
                    v = field._sanitize_data(v)
                    filters.append(bool_string + '{}{}{}'.format(k, middle, v))

        else:
            for k, v in kwargs.items():
                filters.append('{}={}'.format(k, v))
        return filters

    async def filter(self, **kwargs):
        filters = self.calc_filters(kwargs)

        condition = ' AND '.join(filters)

        db_request = {
            'select': '*',
            'table_name': self.model.table_name,
            'action': 'db__select',
            'condition': condition
        }

        if self.model._ordering:
            db_request.update({'ordering': self.model._ordering})

        request = self.db_manager.request(db_request)
        return [self._model_constructor(r) for r in await request]

    async def filter_m2m(self, m2m_filter):
        m2m_filter.update({'select': '*', 'action': 'db__m2m'})
        if self.model._ordering:
            m2m_filter.update({'ordering': self.model._ordering})

        results = await self.db_manager.request(m2m_filter)
        if results.__class__.__name__ == 'Record':
            results = [results, ]

        return [self._model_constructor(r) for r in results]

    async def exclude(self, **kwargs):
        filters = self.calc_filters(kwargs, exclude=True)
        condition = ' AND '.join(filters)

        db_request = {
            'select': '*',
            'table_name': self.model.table_name,
            'action': 'db__select',
            'condition': condition
        }

        if self.model._ordering:
            db_request.update({'ordering': self.model._ordering})

        request = await self.db_manager.request(db_request)
        return [self._model_constructor(r) for r in request]

    async def m2m(self, table_name, my_column, other_column, my_id):
        db_request = {
            'select': other_column,
            'table_name': table_name,
            'action': 'db__select',
            'condition': '{my_column}={my_id}'.format(
                my_column=my_column,
                my_id=my_id,
            )
        }

        if self.model._ordering:
            db_request.update({'ordering': self.model._ordering})

        request = await self.db_manager.request(db_request)
        return [self._model_constructor(r) for r in request]


class ModelManager(Queryset):
    def __init__(self, model):
        self.model = model
        super().__init__(model)

    async def save(self, instanced_model):
        # performs the database save
        fields, field_data = [], []
        for k, data in instanced_model.data.items():
            f_class = getattr(instanced_model.__class__, k)

            field_name = f_class.field_name or k
            data = f_class._sanitize_data(data)

            fields.append(field_name)
            field_data.append(data)

        db_request = {
            'table_name': self.model.table_name,
            'action': (
                getattr(
                    instanced_model, instanced_model._orm_pk
                ) and 'db__update' or 'db__create'
            ),
            'id_data': '{}={}'.format(
                instanced_model._db_pk,
                getattr(instanced_model, instanced_model._orm_pk),
            ),
            'field_names': ', '.join(fields),
            'field_values': ', '.join(field_data),
            'condition': '{}={}'.format(
                instanced_model._db_pk,
                getattr(instanced_model, instanced_model._orm_pk)
            )
        }
        try:
            response = await self.db_manager.request(db_request)
        except UniqueViolationError:
            raise ModelError('The model violates a unique constraint')

        self._model_constructor(response, instanced_model)

        # now we have to save the m2m relations: m2m_data
        fields, field_data = [], []
        for k, data in instanced_model.m2m_data.items():
            # for each of the m2m fields in the model, we have to check
            # if the table register already exists in the table otherwise
            # and delete the ones that are not in the list

            # first get the table_name
            cls_field = getattr(instanced_model.__class__, k)
            table_name = cls_field.table_name
            foreign_column = cls_field.foreign_key

            model_column = instanced_model.table_name

            model_id = getattr(instanced_model, instanced_model._orm_pk)

            db_request = {
                'table_name': table_name,
                'action': 'db__create',
                'field_names': ', '.join([model_column, foreign_column]),
                'field_values': ', '.join([str(model_id), str(data)]),
                # 'ordering': 'id',
            }

            if isinstance(data, list):
                for d in data:
                    await self.db_manager.request(db_request)
                    db_request.update({
                        'field_values': ', '.join([str(model_id), str(d)])
                    })
                    await self.db_manager.request(db_request)
            else:
                await self.db_manager.request(db_request)

    async def delete(self, instanced_model):
        db_request = {
            'select': '*',
            'table_name': self.model.table_name,
            'action': 'db__delete',
            'id_data': '{}={}'.format(
                instanced_model._db_pk,
                getattr(instanced_model, instanced_model._db_pk)
            )
        }
        response = await self.db_manager.request(db_request)
        return response

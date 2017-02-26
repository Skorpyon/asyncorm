class GeneralManager(object):
    # things that belong to all the diff databases managers    @classmethod
    pass


class PostgresManager(GeneralManager):

    def __init__(self, conn_data):
        self.conn_data = conn_data
        self.conn = None

    @property
    def _object__create(self):
        return (
            'INSERT INTO {table_name} ({field_names}) VALUES ({field_values});'
        )

    @property
    def _object__select(self):
        return 'SELECT * FROM {table_name} WHERE {condition};'

    @property
    def _object__select_all(self):
        return 'SELECT * FROM {table_name} ;'

    @property
    def _object__update(self):
        return '''UPDATE ONLY {table_name}
            SET ({field_names}) = ({field_values})
            WHERE {_fk_db_fieldname}={model_id} ;
        '''

    @property
    def _object__delete(self):
        return 'DELETE FROM {table_name} WHERE {id_data};'

    async def get_conn(self):
        import asyncpg
        if not self.conn:
            pool = await asyncpg.create_pool(**self.conn_data)
            self.conn = await pool.acquire()
        return self.conn

    async def _request(self, request_dict):
        query = getattr(self, request_dict['action']).format(**request_dict)
        conn = await self.get_conn()

        if '__select' not in request_dict['action']:
            async with conn.transaction():
                await conn.execute(query)
                if request_dict['action'] != '_object__delete':
                    query = getattr(self, '_object__select')

                    if request_dict['action'] == '_object__create':
                        query = query.replace('WHERE {condition}', '')
                        query = query.format(**request_dict)
                        result = await conn.fetch(query)
                        return result[-1]
                    query = query.format(**request_dict)
                    result = await conn.fetch(query)
                    return result[0]
                else:
                    return None
        else:
            return await conn.fetch(query)

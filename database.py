class GeneralManager(object):
    # things that belong to all the diff databases managers    @classmethod

    def __init__(self, conn_data):
        self.conn_data = conn_data
        self.conn = None


class PostgresManager(GeneralManager):

    @property
    def _object__create(self):
        return '''
            INSERT INTO {table_name} ({field_names}) VALUES ({field_values})
            RETURNING * ;
        '''

    @property
    def _object__select(self):
        return 'SELECT * FROM {table_name} WHERE {condition} ;'

    @property
    def _object__select_all(self):
        return 'SELECT * FROM {table_name} ;'

    @property
    def _object__update(self):
        return '''
            UPDATE ONLY {table_name}
            SET ({field_names}) = ({field_values})
            WHERE {_fk_db_fieldname}={model_id}
            RETURNING * ;
        '''

    @property
    def _object__delete(self):
        return 'DELETE FROM {table_name} WHERE {id_data} ;'

    async def get_conn(self):
        import asyncpg
        if not self.conn:
            pool = await asyncpg.create_pool(**self.conn_data)
            self.conn = await pool.acquire()
        return self.conn

    async def request(self, request_dict):
        query = getattr(self, request_dict['action']).format(**request_dict)
        conn = await self.get_conn()

        async with conn.transaction():
            result = await conn.fetch(query)
            if '__select' not in request_dict['action']:
                if request_dict['action'] != '_object__delete':
                    return result[0]
                else:
                    return None
            else:
                return result

    async def transaction_insert(self, queries):
        conn = await self.get_conn()
        async with conn.transaction():
            for query in queries:
                await conn.execute(query)

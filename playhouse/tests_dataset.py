import datetime
import operator
import os
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import unittest

from peewee import *
from playhouse.dataset import DataSet
from playhouse.dataset import Table


db = SqliteDatabase('tmp.db')

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(primary_key=True)

class Note(BaseModel):
    user = ForeignKeyField(User)
    content = TextField()
    timestamp = DateTimeField()

class Category(BaseModel):
    name = CharField()
    parent = ForeignKeyField('self', null=True)


class TestDataSet(unittest.TestCase):
    names = ['charlie', 'huey', 'peewee', 'mickey', 'zaizee']

    def setUp(self):
        if os.path.exists('tmp.db'):
            os.unlink('tmp.db')
        db.connect()
        db.create_tables([User, Note, Category])

        self.dataset = DataSet('sqlite:///tmp.db')

    def tearDown(self):
        self.dataset.close()
        db.close()

    def create_users(self, n=2):
        user = self.dataset['user']
        for i in range(min(n, len(self.names))):
            user.insert(username=self.names[i])

    def test_introspect(self):
        tables = sorted(self.dataset.tables)
        self.assertEqual(tables, ['category', 'note', 'user'])

        user = self.dataset['user']
        columns = sorted(user.columns)
        self.assertEqual(columns, ['username'])

        note = self.dataset['note']
        columns = sorted(note.columns)
        self.assertEqual(columns, ['content', 'id', 'timestamp', 'user'])

        category = self.dataset['category']
        columns = sorted(category.columns)
        self.assertEqual(columns, ['id', 'name', 'parent'])

    def assertQuery(self, query, expected, sort_key='id'):
        key = operator.itemgetter(sort_key)
        self.assertEqual(
            sorted(list(query), key=key),
            sorted(expected, key=key))

    def test_insert(self):
        self.create_users()
        user = self.dataset['user']

        expected = [
            {'username': 'charlie'},
            {'username': 'huey'}]
        self.assertQuery(user.all(), expected, 'username')

        user.insert(username='mickey', age=5)
        expected = [
            {'username': 'charlie', 'age': None},
            {'username': 'huey', 'age': None},
            {'username': 'mickey', 'age': 5}]
        self.assertQuery(user.all(), expected, 'username')

        query = user.find(username='charlie')
        expected = [{'username': 'charlie', 'age': None}]
        self.assertQuery(query, expected, 'username')

        self.assertEqual(
            user.find_one(username='mickey'),
            {'username': 'mickey', 'age': 5})

        self.assertTrue(user.find_one(username='xx') is None)

    def test_update(self):
        self.create_users()
        user = self.dataset['user']

        self.assertEqual(user.update(favorite_color='green'), 2)
        expected = [
            {'username': 'charlie', 'favorite_color': 'green'},
            {'username': 'huey', 'favorite_color': 'green'}]
        self.assertQuery(user.all(), expected, 'username')

        res = user.update(
            favorite_color='blue',
            username='huey',
            columns=['username'])
        self.assertEqual(res, 1)
        expected[1]['favorite_color'] = 'blue'
        self.assertQuery(user.all(), expected, 'username')

    def test_delete(self):
        self.create_users()
        user = self.dataset['user']
        self.assertEqual(user.delete(username='huey'), 1)
        self.assertEqual(list(user.all()), [{'username': 'charlie'}])

    def test_find(self):
        self.create_users(5)
        user = self.dataset['user']

        def assertUsernames(query, expected):
            self.assertEqual(
                sorted(row['username'] for row in query),
                sorted(expected))

        assertUsernames(user.all(), self.names)
        assertUsernames(user.find(), self.names)
        assertUsernames(user.find(username='charlie'), ['charlie'])
        assertUsernames(user.find(username='missing'), [])

        user.update(favorite_color='green')
        for username in ['zaizee', 'huey']:
            user.update(
                favorite_color='blue',
                username=username,
                columns=['username'])

        assertUsernames(
            user.find(favorite_color='green'),
            ['charlie', 'mickey', 'peewee'])
        assertUsernames(
            user.find(favorite_color='blue'),
            ['zaizee', 'huey'])
        assertUsernames(
            user.find(favorite_color='green', username='peewee'),
            ['peewee'])

        self.assertEqual(
            user.find_one(username='charlie'),
            {'username': 'charlie', 'favorite_color': 'green'})

    def test_magic_methods(self):
        self.create_users(5)
        user = self.dataset['user']

        # __len__()
        self.assertEqual(len(user), 5)

        # __iter__()
        users = sorted([u for u in user], key=operator.itemgetter('username'))
        self.assertEqual(users[0], {'username': 'charlie'})
        self.assertEqual(users[-1], {'username': 'zaizee'})

        # __contains__()
        self.assertTrue('user' in self.dataset)
        self.assertFalse('missing' in self.dataset)

    def test_foreign_keys(self):
        user = self.dataset['user']
        user.insert(username='charlie')

        note = self.dataset['note']
        for i in range(1, 4):
            note.insert(
                content='note %s' % i,
                timestamp=datetime.date(2014, 1, i),
                user='charlie')

        notes = sorted(note.all(), key=operator.itemgetter('id'))
        self.assertEqual(notes[0], {
            'content': 'note 1',
            'id': 1,
            'timestamp': datetime.datetime(2014, 1, 1),
            'user': 'charlie'})
        self.assertEqual(notes[-1], {
            'content': 'note 3',
            'id': 3,
            'timestamp': datetime.datetime(2014, 1, 3),
            'user': 'charlie'})

        user.insert(username='mickey')
        note.update(user='mickey', id=3, columns=['id'])

        self.assertEqual(note.find(user='charlie').count(), 2)
        self.assertEqual(note.find(user='mickey').count(), 1)

        category = self.dataset['category']
        category.insert(name='c1')
        c1 = category.find_one(name='c1')
        self.assertEqual(c1, {'id': 1, 'name': 'c1', 'parent': None})

        category.insert(name='c2', parent=1)
        c2 = category.find_one(parent=1)
        self.assertEqual(c2, {'id': 2, 'name': 'c2', 'parent': 1})

        self.assertEqual(category.delete(parent=1), 1)
        self.assertEqual(category.all(), [c1])

    def test_transactions(self):
        user = self.dataset['user']
        with self.dataset.transaction() as txn:
            user.insert(username='u1')
            with self.dataset.transaction() as txn2:
                user.insert(username='u2')
                txn2.rollback()

            with self.dataset.transaction() as txn3:
                user.insert(username='u3')
                with self.dataset.transaction() as txn4:
                    user.insert(username='u4')
                txn3.rollback()

            with self.dataset.transaction() as txn5:
                user.insert(username='u5')
                with self.dataset.transaction() as txn6:
                    with self.dataset.transaction() as txn7:
                        user.insert(username='u6')
                        txn7.rollback()
                    user.insert(username='u7')

            user.insert(username='u8')

        self.assertQuery(user.all(), [
            {'username': 'u1'},
            {'username': 'u5'},
            {'username': 'u7'},
            {'username': 'u8'},
        ], 'username')

    def test_export(self):
        self.create_users()
        user = self.dataset['user']

        buf = StringIO()
        self.dataset.freeze(user.all(), 'json', file_obj=buf)
        self.assertEqual(buf.getvalue(), (
            '[{"username": "charlie"}, {"username": "huey"}]'))

        buf = StringIO()
        self.dataset.freeze(user.all(), 'csv', file_obj=buf)
        self.assertEqual(buf.getvalue().splitlines(), [
            'username',
            'charlie',
            'huey'])